"""
Table Maintenance Operations
=============================
Low-level Iceberg maintenance: compaction, snapshot expiration, and snapshot listing.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pyarrow as pa
from pyiceberg.catalog import Catalog
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.table import Table

from iceberg.tables import TableNotFoundException, TableOperationError


@dataclass
class CompactionResult:
    """Result of a table compaction operation."""
    files_before: int
    files_after: int
    size_before_bytes: int
    size_after_bytes: int
    new_snapshot_id: Optional[int]


@dataclass
class ExpireSnapshotsResult:
    """Result of expiring old snapshots."""
    expired_count: int
    remaining_count: int


@dataclass
class SnapshotDetail:
    """Detailed info about a single snapshot."""
    snapshot_id: int
    parent_snapshot_id: Optional[int]
    timestamp_ms: int
    timestamp_utc: str
    operation: str
    summary: Dict[str, str]
    manifest_list: Optional[str]


def _load_table(catalog: Catalog, table_name: str, namespace: str) -> Table:
    """Load table or raise TableNotFoundException."""
    identifier = (namespace.strip().lower(), table_name.strip().lower())
    try:
        return catalog.load_table(identifier)
    except NoSuchTableError as e:
        raise TableNotFoundException(f"Table '{namespace}.{table_name}' not found.") from e


def compact_table(catalog: Catalog, table_name: str, namespace: str = "default") -> CompactionResult:
    """
    Naive compaction: reads all data files, rewrites as a single consolidated Parquet file.

    This mirrors the concept of Spark's rewriteDataFiles action but uses a simple
    read-all → overwrite approach suitable for a local development environment.

    Production approach: Use Spark's `rewriteDataFiles` or Iceberg's built-in
    compaction procedures for incremental bin-packing.
    """
    table = _load_table(catalog, table_name, namespace)
    identifier = (namespace.strip().lower(), table_name.strip().lower())

    # Capture pre-compaction stats
    current_snap = table.current_snapshot()
    if not current_snap or not current_snap.summary:
        raise TableOperationError(f"Table '{namespace}.{table_name}' has no data to compact.")

    props = current_snap.summary.additional_properties
    files_before = int(props.get("total-data-files", "0"))
    size_before = int(props.get("total-files-size-in-bytes", "0"))

    if files_before <= 1:
        # Already compact
        return CompactionResult(
            files_before=files_before,
            files_after=files_before,
            size_before_bytes=size_before,
            size_after_bytes=size_before,
            new_snapshot_id=current_snap.snapshot_id,
        )

    # ponytail: naive full-table rewrite — ceiling: O(table_size) memory.
    # Upgrade path: Spark rewriteDataFiles with bin-packing for TB-scale tables.
    try:
        # Read all data via PyArrow scan
        arrow_table: pa.Table = table.scan().to_arrow()

        # Overwrite: delete all existing data and write consolidated file
        table.overwrite(arrow_table)

        # Reload to get fresh stats
        table = catalog.load_table(identifier)
        new_snap = table.current_snapshot()
        new_props = new_snap.summary.additional_properties if new_snap and new_snap.summary else {}
        files_after = int(new_props.get("total-data-files", "1"))
        size_after = int(new_props.get("total-files-size-in-bytes", "0"))

        return CompactionResult(
            files_before=files_before,
            files_after=files_after,
            size_before_bytes=size_before,
            size_after_bytes=size_after,
            new_snapshot_id=new_snap.snapshot_id if new_snap else None,
        )
    except Exception as e:
        raise TableOperationError(f"Compaction failed for '{namespace}.{table_name}': {str(e)}") from e


def expire_snapshots(
    catalog: Catalog,
    table_name: str,
    namespace: str = "default",
    older_than_days: int = 30,
) -> ExpireSnapshotsResult:
    """
    Expire snapshots older than the specified threshold.

    Uses PyIceberg's table.maintenance.expire_snapshots() API (0.6+) to remove
    old snapshots while preserving the current snapshot.
    """
    table = _load_table(catalog, table_name, namespace)
    identifier = (namespace.strip().lower(), table_name.strip().lower())

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    cutoff_ms = int(cutoff.timestamp() * 1000)

    # Collect snapshots eligible for expiration
    all_snapshots = list(table.history())
    current_snap = table.current_snapshot()
    current_id = current_snap.snapshot_id if current_snap else None

    to_expire = [
        s for s in all_snapshots
        if s.timestamp_ms < cutoff_ms and s.snapshot_id != current_id
    ]

    if not to_expire:
        return ExpireSnapshotsResult(expired_count=0, remaining_count=len(all_snapshots))

    # PyIceberg 0.6+ exposes table.maintenance.expire_snapshots()
    try:
        with table.maintenance.expire_snapshots() as expire:
            for snap in to_expire:
                expire.by_id(snap.snapshot_id)
    except AttributeError:
        # Fallback: older PyIceberg without maintenance API — use older_than approach
        try:
            table.maintenance.expire_snapshots().older_than(cutoff).commit()
        except AttributeError:
            # Neither API available — cannot expire, report as no-op
            return ExpireSnapshotsResult(expired_count=0, remaining_count=len(all_snapshots))
    except Exception as e:
        raise TableOperationError(f"Snapshot expiration failed: {str(e)}") from e

    # Reload to verify
    table = catalog.load_table(identifier)
    remaining = len(list(table.history()))
    return ExpireSnapshotsResult(expired_count=len(to_expire), remaining_count=remaining)


def list_snapshots(catalog: Catalog, table_name: str, namespace: str = "default") -> List[SnapshotDetail]:
    """Return detailed snapshot history for a table."""
    table = _load_table(catalog, table_name, namespace)

    details: List[SnapshotDetail] = []
    for entry in table.history():
        snap = table.snapshot_by_id(entry.snapshot_id) if hasattr(table, "snapshot_by_id") else None
        summary_dict: Dict[str, str] = {}
        operation = "append"
        manifest_list = None

        if snap:
            if snap.summary:
                summary_dict = dict(snap.summary.additional_properties)
                operation = str(snap.summary.operation.value) if snap.summary.operation else "append"
            manifest_list = snap.manifest_list

        ts_utc = datetime.fromtimestamp(entry.timestamp_ms / 1000.0, tz=timezone.utc).isoformat()

        details.append(SnapshotDetail(
            snapshot_id=entry.snapshot_id,
            parent_snapshot_id=snap.parent_snapshot_id if snap else None,
            timestamp_ms=entry.timestamp_ms,
            timestamp_utc=ts_utc,
            operation=operation,
            summary=summary_dict,
            manifest_list=manifest_list,
        ))

    return details
