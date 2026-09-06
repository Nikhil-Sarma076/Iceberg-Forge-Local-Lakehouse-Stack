"""
Table Management Service
========================
High-level service orchestrating Iceberg catalog operations,
ingestion pipelines, and API responses.
"""

from typing import List, Optional
from app.models.table import (
    AppendTableRequest,
    CreateTableRequest,
    FieldSchemaModel,
    SnapshotModel,
    TableDeleteResponse,
    TableDetailResponse,
    TableSummaryModel,
    WriteTableRequest,
)
from app.services.ingestion_service import IngestionService
from iceberg.tables import (
    IcebergTableManager,
    TableDetailMetadata,
    TableMetadataSummary,
)


class TableService:
    """
    Coordinates ingestion service and Iceberg table manager.
    """

    def __init__(
        self,
        table_manager: IcebergTableManager,
        ingestion_service: Optional[IngestionService] = None,
    ):
        self.table_manager = table_manager
        self.ingestion_service = ingestion_service or IngestionService()

    def _convert_detail_to_response(
        self,
        detail: TableDetailMetadata,
        source_file: Optional[str] = None,
        detected_format: Optional[str] = None,
    ) -> TableDetailResponse:
        """Helper to map internal TableDetailMetadata to Pydantic TableDetailResponse."""
        fields = [
            FieldSchemaModel(
                field_id=f["field_id"],
                name=f["name"],
                type=f["type"],
                required=f["required"],
                doc=f.get("doc"),
            )
            for f in detail.schema_fields
        ]

        snapshots = [
            SnapshotModel(
                snapshot_id=s.snapshot_id,
                parent_snapshot_id=s.parent_snapshot_id,
                timestamp_ms=s.timestamp_ms,
                operation=s.operation,
                summary=s.summary,
                manifest_list=s.manifest_list,
            )
            for s in detail.snapshots
        ]

        return TableDetailResponse(
            name=detail.name,
            namespace=detail.namespace,
            identifier=detail.identifier,
            location=detail.location,
            format_version=detail.format_version,
            current_snapshot_id=detail.current_snapshot_id,
            total_records=detail.total_records,
            total_files=detail.total_files,
            total_data_size_bytes=detail.total_data_size_bytes,
            schema_fields=fields,
            properties=detail.properties,
            snapshots=snapshots,
            created_at_utc=detail.created_at_utc,
            inferred_from_file=source_file,
            detected_format=detected_format,
        )

    def create_table(self, request: CreateTableRequest) -> TableDetailResponse:
        """
        Executes full ingestion pipeline:
        1. Resolve file & infer schema with PyArrow
        2. Create Iceberg table in catalog
        3. Write initial data batch to MinIO S3
        4. Return enriched table details
        """
        arrow_table, iceberg_schema, detected_format, resolved_path = (
            self.ingestion_service.load_and_infer(request.file)
        )

        detail_metadata = self.table_manager.create_table_from_arrow(
            table_name=request.name,
            arrow_table=arrow_table,
            iceberg_schema=iceberg_schema,
            namespace=request.namespace or "default",
        )

        return self._convert_detail_to_response(
            detail_metadata,
            source_file=resolved_path,
            detected_format=detected_format,
        )

    def append_table(self, table_name: str, request: AppendTableRequest) -> TableDetailResponse:
        """
        Appends records from an input file into an existing Iceberg table.
        """
        arrow_table, detected_format, resolved_path = (
            self.ingestion_service.load_table_data(request.file)
        )

        detail_metadata = self.table_manager.append_data(
            table_name=table_name,
            arrow_table=arrow_table,
            namespace=request.namespace or "default",
        )

        return self._convert_detail_to_response(
            detail_metadata,
            source_file=resolved_path,
            detected_format=detected_format,
        )

    def write_table(self, table_name: str, request: "WriteTableRequest") -> TableDetailResponse:
        """
        Writes data into an existing table using append, overwrite, or merge mode.
        """
        arrow_table, detected_format, resolved_path = (
            self.ingestion_service.load_table_data(request.file)
        )

        detail_metadata = self.table_manager.write_data(
            table_name=table_name,
            arrow_table=arrow_table,
            mode=request.mode.value if hasattr(request.mode, "value") else str(request.mode),
            merge_key=request.merge_key,
            namespace=request.namespace or "default",
        )

        return self._convert_detail_to_response(
            detail_metadata,
            source_file=resolved_path,
            detected_format=detected_format,
        )

    def get_table(self, table_name: str, namespace: str = "default") -> TableDetailResponse:
        """
        Fetches detailed table metadata.
        """
        detail_metadata = self.table_manager.get_table(table_name, namespace=namespace)
        return self._convert_detail_to_response(detail_metadata)

    def list_tables(self, namespace: str = "default") -> List[TableSummaryModel]:
        """
        Lists all tables within the namespace.
        """
        summaries = self.table_manager.list_tables(namespace=namespace)
        return [
            TableSummaryModel(
                name=s.name,
                namespace=s.namespace,
                identifier=s.identifier,
                location=s.location,
                total_records=s.total_records,
                current_snapshot_id=s.current_snapshot_id,
                schema_fields_count=s.schema_fields_count,
            )
            for s in summaries
        ]

    def delete_table(
        self, table_name: str, namespace: str = "default", purge: bool = False
    ) -> TableDeleteResponse:
        """
        Drops table from Iceberg catalog.
        """
        self.table_manager.drop_table(table_name, namespace=namespace, purge=purge)
        ident = f"{namespace}.{table_name}"
        return TableDeleteResponse(
            status="deleted",
            identifier=ident,
            message=f"Table '{ident}' was successfully removed from the catalog.",
        )
