"""
Iceberg Table Operations
========================
Encapsulates low-level PyIceberg table manipulation:
creation, appending, metadata inspection, listing, and dropping.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import pyarrow as pa
from pyiceberg.catalog import Catalog
from pyiceberg.exceptions import (
    NoSuchNamespaceError,
    NoSuchTableError,
    TableAlreadyExistsError,
)
from pyiceberg.schema import Schema
from pyiceberg.table import Table, Snapshot

from iceberg.schema import format_schema_summary


class TableOperationError(Exception):
    """Base exception for table operation failures."""
    pass


class TableAlreadyExistsException(TableOperationError):
    """Raised when attempting to create a table that already exists."""
    pass


class TableNotFoundException(TableOperationError):
    """Raised when a requested table is not found."""
    pass


@dataclass
class SnapshotInfo:
    snapshot_id: int
    parent_snapshot_id: Optional[int]
    timestamp_ms: int
    operation: str
    summary: Dict[str, str]
    manifest_list: Optional[str]


@dataclass
class TableMetadataSummary:
    name: str
    namespace: str
    identifier: str
    location: str
    total_records: int
    current_snapshot_id: Optional[int]
    schema_fields_count: int


@dataclass
class TableDetailMetadata:
    name: str
    namespace: str
    identifier: str
    location: str
    format_version: int
    current_snapshot_id: Optional[int]
    total_records: int
    total_files: int
    total_data_size_bytes: int
    schema_fields: List[Dict[str, Any]]
    properties: Dict[str, Any]
    snapshots: List[SnapshotInfo]
    created_at_utc: Optional[str] = None


class IcebergTableManager:
    """
    Manages Apache Iceberg table lifecycle operations.
    """

    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    def _format_identifier(self, table_name: str, namespace: str = "default") -> Tuple[str, str]:
        """Returns standard tuple identifier for PyIceberg (namespace, table_name)."""
        clean_ns = namespace.strip().lower()
        clean_name = table_name.strip().lower()
        return (clean_ns, clean_name)

    def _ensure_namespace(self, namespace: str = "default") -> None:
        """Ensures the namespace exists in the catalog."""
        try:
            self.catalog.create_namespace(namespace)
        except Exception:
            # Namespace may already exist or catalog does not require explicit creation
            pass

    def create_table_from_arrow(
        self,
        table_name: str,
        arrow_table: pa.Table,
        iceberg_schema: Schema,
        namespace: str = "default",
        properties: Optional[Dict[str, str]] = None,
    ) -> TableDetailMetadata:
        """
        Creates an Iceberg table and ingests the PyArrow dataset into it.
        """
        identifier = self._format_identifier(table_name, namespace)
        self._ensure_namespace(namespace)

        table_properties = properties or {
            "write.format.default": "parquet",
            "created_by": "local-iceberg-ingestion-toolkit",
        }

        try:
            table: Table = self.catalog.create_table(
                identifier=identifier,
                schema=iceberg_schema,
                properties=table_properties,
            )
        except TableAlreadyExistsError as e:
            raise TableAlreadyExistsException(
                f"Table '{namespace}.{table_name}' already exists."
            ) from e
        except Exception as e:
            raise TableOperationError(f"Failed to create table '{namespace}.{table_name}': {str(e)}") from e

        # Append initial data
        try:
            arrow_table = self._cast_to_table_schema(arrow_table, table)
            table.append(arrow_table)
            # Reload table to fetch fresh snapshot metadata
            table = self.catalog.load_table(identifier)
        except Exception as e:
            raise TableOperationError(f"Failed to write data to table '{namespace}.{table_name}': {str(e)}") from e

        return self._extract_table_details(table)

    def append_data(
        self,
        table_name: str,
        arrow_table: pa.Table,
        namespace: str = "default",
    ) -> TableDetailMetadata:
        """
        Appends new PyArrow records to an existing Iceberg table.
        """
        identifier = self._format_identifier(table_name, namespace)
        try:
            table: Table = self.catalog.load_table(identifier)
        except NoSuchTableError as e:
            raise TableNotFoundException(
                f"Table '{namespace}.{table_name}' does not exist."
            ) from e
        except Exception as e:
            raise TableOperationError(f"Error loading table '{namespace}.{table_name}': {str(e)}") from e

        try:
            arrow_table = self._cast_to_table_schema(arrow_table, table)
            table.append(arrow_table)
            table = self.catalog.load_table(identifier)
        except Exception as e:
            raise TableOperationError(f"Failed to append data to table '{namespace}.{table_name}': {str(e)}") from e

        return self._extract_table_details(table)

    def write_data(
        self,
        table_name: str,
        arrow_table: pa.Table,
        mode: str = "append",
        merge_key: Optional[str] = None,
        namespace: str = "default",
    ) -> TableDetailMetadata:
        """
        Writes data to an existing table using one of three modes:

        - append:    add the incoming rows (new snapshot)
        - overwrite: replace ALL existing data with the incoming rows
        - merge:     upsert on `merge_key` — rows in the table whose key matches an
                     incoming row are replaced, non-matching table rows are kept, and
                     brand-new incoming rows are added.

        Merge is implemented as copy-on-write: read the current table, drop the
        matching keys, concatenate the incoming data, then overwrite.
        """
        mode = (mode or "append").strip().lower()
        if mode not in ("append", "overwrite", "merge"):
            raise TableOperationError(f"Unsupported write mode '{mode}'. Use append, overwrite, or merge.")

        identifier = self._format_identifier(table_name, namespace)
        try:
            table: Table = self.catalog.load_table(identifier)
        except NoSuchTableError as e:
            raise TableNotFoundException(f"Table '{namespace}.{table_name}' does not exist.") from e
        except Exception as e:
            raise TableOperationError(f"Error loading table '{namespace}.{table_name}': {str(e)}") from e

        try:
            arrow_table = self._cast_to_table_schema(arrow_table, table)

            if mode == "append":
                table.append(arrow_table)

            elif mode == "overwrite":
                table.overwrite(arrow_table)

            elif mode == "merge":
                if not merge_key:
                    raise TableOperationError("merge mode requires a 'merge_key' column.")
                # Normalize merge_key to match normalized column names (spaces → underscores)
                normalized_merge_key = merge_key.replace(' ', '_')
                column_names = arrow_table.schema.names
                if normalized_merge_key not in column_names:
                    raise TableOperationError(
                        f"merge_key '{merge_key}' (normalized: '{normalized_merge_key}') not found in data columns: {column_names}"
                    )
                merged = self._merge_arrow(table, arrow_table, normalized_merge_key)
                table.overwrite(merged)

            table = self.catalog.load_table(identifier)
        except (TableOperationError,):
            raise
        except Exception as e:
            raise TableOperationError(
                f"Failed to {mode} data on table '{namespace}.{table_name}': {str(e)}"
            ) from e

        return self._extract_table_details(table)

    @staticmethod
    def _merge_arrow(table: Table, incoming: pa.Table, merge_key: str) -> pa.Table:
        """
        Copy-on-write upsert: keep existing rows whose key is NOT in the incoming
        set, then append all incoming rows.

        ponytail: reads the whole table into memory to recompute the merge —
        ceiling is O(table_size) RAM and a full-table rewrite per merge.
        Production upgrade path: Spark `MERGE INTO` or Iceberg row-level deletes
        (merge-on-read), which touch only affected files.
        """
        existing = table.scan().to_arrow()

        # No existing data → merge is just the incoming set.
        if existing.num_rows == 0:
            return incoming

        incoming_keys = set(incoming.column(merge_key).to_pylist())
        # Boolean mask: keep existing rows whose key is not being replaced.
        keep_mask = [k not in incoming_keys for k in existing.column(merge_key).to_pylist()]
        retained = existing.filter(pa.array(keep_mask, type=pa.bool_()))

        # Align columns to the existing table's column order before concat.
        # table.scan().to_arrow() includes PyIceberg internal metadata columns
        # (__fragment_index, __batch_index, __last_in_fragment, __filename) that should
        # not be in the final merged table, so filter them out before alignment.
        # NOTE: concat the *retained* (matching rows dropped) set with incoming — using
        # the unfiltered `existing` here would keep the old rows AND append the updated
        # ones, producing duplicate keys instead of an upsert.
        iceberg_internal_cols = {'__fragment_index', '__batch_index', '__last_in_fragment', '__filename'}
        cols_to_keep = [n for n in existing.schema.names if n not in iceberg_internal_cols]

        retained_clean = retained.select(cols_to_keep)
        incoming_aligned = incoming.select(cols_to_keep)
        return pa.concat_tables([retained_clean, incoming_aligned])

    def get_table(self, table_name: str, namespace: str = "default") -> TableDetailMetadata:
        """
        Retrieves detailed schema and snapshot metadata for a specific table.
        """
        identifier = self._format_identifier(table_name, namespace)
        try:
            table: Table = self.catalog.load_table(identifier)
        except NoSuchTableError as e:
            raise TableNotFoundException(f"Table '{namespace}.{table_name}' not found.") from e
        except Exception as e:
            raise TableOperationError(f"Error fetching table '{namespace}.{table_name}': {str(e)}") from e

        return self._extract_table_details(table)

    def list_tables(self, namespace: str = "default") -> List[TableMetadataSummary]:
        """
        Lists all tables within the specified namespace.
        """
        self._ensure_namespace(namespace)
        try:
            identifiers = self.catalog.list_tables(namespace)
        except NoSuchNamespaceError:
            return []
        except Exception as e:
            raise TableOperationError(f"Failed to list tables in namespace '{namespace}': {str(e)}") from e

        summaries: List[TableMetadataSummary] = []
        for ident in identifiers:
            try:
                table = self.catalog.load_table(ident)
                current_snapshot = table.current_snapshot()
                total_records = 0
                if current_snapshot and current_snapshot.summary:
                    total_records = int(current_snapshot.summary.additional_properties.get("total-records", 0))

                table_name = ident[1] if isinstance(ident, tuple) and len(ident) > 1 else str(ident)
                table_ns = ident[0] if isinstance(ident, tuple) and len(ident) > 1 else namespace

                summaries.append(
                    TableMetadataSummary(
                        name=table_name,
                        namespace=table_ns,
                        identifier=f"{table_ns}.{table_name}",
                        location=table.location(),
                        total_records=total_records,
                        current_snapshot_id=current_snapshot.snapshot_id if current_snapshot else None,
                        schema_fields_count=len(table.schema().fields),
                    )
                )
            except Exception:
                # If a corrupted table cannot be loaded, continue listing other tables
                continue

        return summaries

    def drop_table(self, table_name: str, namespace: str = "default", purge: bool = False) -> bool:
        """
        Drops an Iceberg table from the catalog.
        """
        identifier = self._format_identifier(table_name, namespace)
        try:
            self.catalog.drop_table(identifier)
            return True
        except NoSuchTableError as e:
            raise TableNotFoundException(f"Table '{namespace}.{table_name}' not found.") from e
        except Exception as e:
            raise TableOperationError(f"Failed to drop table '{namespace}.{table_name}': {str(e)}") from e

    @staticmethod
    def _cast_to_table_schema(arrow_table: pa.Table, iceberg_table: Table) -> pa.Table:
        """Cast Arrow table columns to match the Iceberg table's expected Arrow schema."""
        from pyiceberg.io.pyarrow import schema_to_pyarrow
        target_schema = schema_to_pyarrow(iceberg_table.schema())
        if arrow_table.schema.equals(target_schema):
            return arrow_table
        # Cast each column to the target type
        arrays = []
        for field in target_schema:
            try:
                source_col = arrow_table.column(field.name)
            except KeyError:
                # Field not found — likely a column name encoding or case mismatch
                available = arrow_table.schema.names
                raise ValueError(
                    f"Column '{field.name}' (from table schema) not found in incoming data. "
                    f"Available columns: {available}. This may indicate a column name "
                    f"encoding or case mismatch (e.g., 'Customer Id' vs. 'Customer_x20Id')."
                ) from None
            if not source_col.type.equals(field.type):
                source_col = source_col.cast(field.type)
            arrays.append(source_col)
        return pa.table(arrays, schema=target_schema)

    def _extract_table_details(self, table: Table) -> TableDetailMetadata:
        """
        Extracts comprehensive metadata from a PyIceberg Table object.
        """
        schema_summary = format_schema_summary(table.schema())

        # Extract snapshot history
        snapshots_info: List[SnapshotInfo] = []
        for s in table.history():
            matching_snap = table.snapshot_by_id(s.snapshot_id) if hasattr(table, "snapshot_by_id") else None
            summary_dict = {}
            operation = "append"
            if matching_snap and matching_snap.summary:
                summary_dict = dict(matching_snap.summary.additional_properties)
                operation = str(matching_snap.summary.operation.value) if matching_snap.summary.operation else "append"
            manifest_list = matching_snap.manifest_list if matching_snap else None

            snapshots_info.append(
                SnapshotInfo(
                    snapshot_id=s.snapshot_id,
                    parent_snapshot_id=matching_snap.parent_snapshot_id if matching_snap else None,
                    timestamp_ms=s.timestamp_ms,
                    operation=operation,
                    summary=summary_dict,
                    manifest_list=manifest_list,
                )
            )

        current_snap = table.current_snapshot()
        total_records = 0
        total_files = 0
        total_data_size = 0

        if current_snap and current_snap.summary:
            props = current_snap.summary.additional_properties
            total_records = int(props.get("total-records", "0"))
            total_files = int(props.get("total-data-files", "0"))
            total_data_size = int(props.get("total-files-size-in-bytes", "0"))

        created_at_utc = None
        if hasattr(table, "metadata") and hasattr(table.metadata, "last_updated_ms"):
            created_at_utc = datetime.fromtimestamp(
                table.metadata.last_updated_ms / 1000.0, tz=timezone.utc
            ).isoformat()

        # Format identifier string
        if isinstance(table.identifier, tuple):
            # PyIceberg returns (catalog, namespace, table) or (namespace, table)
            name = table.identifier[-1]
            ns = table.identifier[-2] if len(table.identifier) >= 2 else "default"
        else:
            ns = "default"
            name = str(table.identifier)

        return TableDetailMetadata(
            name=name,
            namespace=ns,
            identifier=f"{ns}.{name}",
            location=table.location(),
            format_version=table.metadata.format_version if hasattr(table, "metadata") else 2,
            current_snapshot_id=current_snap.snapshot_id if current_snap else None,
            total_records=total_records,
            total_files=total_files,
            total_data_size_bytes=total_data_size,
            schema_fields=schema_summary,
            properties=dict(table.properties),
            snapshots=snapshots_info,
            created_at_utc=created_at_utc,
        )
