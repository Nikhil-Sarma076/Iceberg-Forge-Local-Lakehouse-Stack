"""
API Routes
==========
FastAPI endpoints for table ingestion, schema inference, Iceberg management,
async job queue, table maintenance, and schema evolution.
"""

import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File

from app.api.dependencies import get_table_service, get_catalog_dependency
from app.config.settings import settings
from app.models.job import JobIngestRequest, JobResponse, JobSubmitResponse
from app.models.table import (
    AppendTableRequest,
    CompactResponse,
    CreateTableRequest,
    ErrorResponse,
    ExpireSnapshotsRequest,
    ExpireSnapshotsResponse,
    FieldSchemaModel,
    HealthResponse,
    PreviewTableResponse,
    QueryRequest,
    QueryResponse,
    SchemaEvolutionRequest,
    SchemaEvolutionResponse,
    SnapshotDetailModel,
    TableDeleteResponse,
    TableDetailResponse,
    TableSummaryModel,
    WriteTableRequest,
)
from app.services.ingestion_service import DatasetResolutionError, IngestionService
from app.services.table_service import TableService
from app.services import job_service
from app.services.trino_service import TrinoService
from iceberg.schema import SchemaInferenceError
from iceberg.tables import (
    TableAlreadyExistsException,
    TableNotFoundException,
    TableOperationError,
)

router = APIRouter()


# =============================================================================
# System
# =============================================================================


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """Returns the operational status of the service."""
    return HealthResponse(status="ok", version=settings.APP_VERSION)


# =============================================================================
# Preview (File Upload)
# =============================================================================


@router.post("/v1/preview", response_model=PreviewTableResponse, summary="Upload and Preview Iceberg Schema", tags=["Tables"])
async def preview_schema(file: UploadFile = File(...)):
    """Upload a file and preview its inferred Iceberg schema without creating a table."""
    uid = str(uuid.uuid4())[:8]
    safe_name = file.filename.replace(" ", "_")
    server_filename = f"{uid}_{safe_name}"
    path = Path(settings.SAMPLE_DATA_DIR) / server_filename
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion = IngestionService()
    try:
        # Preview only needs column TYPES for the UI schema view,
        # so we sample up to SAMPLE_ROW_LIMIT rows instead of loading the whole file.
        from iceberg.schema import SAMPLE_ROW_LIMIT
        arrow_table, iceberg_schema, detected_format, _ = ingestion.load_and_infer(
            server_filename, sample_rows=SAMPLE_ROW_LIMIT
        )
        fields = [
            {"field_id": f.field_id, "name": f.name, "type": str(f.field_type), "required": f.required}
            for f in iceberg_schema.fields
        ]
        return PreviewTableResponse(
            file=server_filename,
            original_filename=file.filename,
            detected_format=detected_format,
            row_count=arrow_table.num_rows,
            schema_fields=fields,
        )
    except Exception as e:
        if path.exists():
            path.unlink()
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Table CRUD
# =============================================================================


@router.post(
    "/v1/tables",
    response_model=TableDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create & Ingest Iceberg Table",
    description="Validates dataset, infers schema via PyArrow, creates Iceberg table, writes data to MinIO, and registers catalog metadata.",
    tags=["Tables"],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid schema or format"},
        404: {"model": ErrorResponse, "description": "File not found"},
        409: {"model": ErrorResponse, "description": "Table already exists"},
        500: {"model": ErrorResponse, "description": "Catalog or write error"},
    },
)
async def create_table(
    payload: CreateTableRequest,
    service: TableService = Depends(get_table_service),
) -> TableDetailResponse:
    """Ingests a CSV, JSON, or Parquet dataset into a newly created Apache Iceberg table."""
    try:
        return service.create_table(payload)
    except (DatasetResolutionError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (SchemaInferenceError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TableAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except TableOperationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {str(e)}")


@router.get(
    "/v1/tables",
    response_model=List[TableSummaryModel],
    summary="List Iceberg Tables",
    tags=["Tables"],
)
async def list_tables(
    namespace: str = Query("default", description="Iceberg catalog namespace"),
    service: TableService = Depends(get_table_service),
) -> List[TableSummaryModel]:
    """Lists summary information for all tables in the Iceberg catalog."""
    try:
        return service.list_tables(namespace=namespace)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/v1/tables/{table_name}",
    response_model=TableDetailResponse,
    summary="Describe Iceberg Table",
    tags=["Tables"],
    responses={404: {"model": ErrorResponse}},
)
async def get_table(
    table_name: str,
    namespace: str = Query("default", description="Iceberg catalog namespace"),
    service: TableService = Depends(get_table_service),
) -> TableDetailResponse:
    """Fetches detailed metadata, schema, and commit history for a specific table."""
    try:
        return service.get_table(table_name=table_name, namespace=namespace)
    except TableNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/v1/tables/{table_name}",
    response_model=TableDeleteResponse,
    summary="Delete Iceberg Table",
    tags=["Tables"],
    responses={404: {"model": ErrorResponse}},
)
async def delete_table(
    table_name: str,
    namespace: str = Query("default", description="Iceberg catalog namespace"),
    purge: bool = Query(False, description="Whether to purge underlying data files"),
    service: TableService = Depends(get_table_service),
) -> TableDeleteResponse:
    """Drops an existing Iceberg table."""
    try:
        return service.delete_table(table_name=table_name, namespace=namespace, purge=purge)
    except TableNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/v1/tables/{table_name}/append",
    response_model=TableDetailResponse,
    summary="Append Data to Iceberg Table",
    tags=["Tables"],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def append_to_table(
    table_name: str,
    payload: AppendTableRequest,
    service: TableService = Depends(get_table_service),
) -> TableDetailResponse:
    """Appends new data to an existing Iceberg table and creates a new commit snapshot."""
    try:
        return service.append_table(table_name=table_name, request=payload)
    except (DatasetResolutionError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (SchemaInferenceError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TableNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TableOperationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {str(e)}")


@router.post(
    "/v1/tables/{table_name}/write",
    response_model=TableDetailResponse,
    summary="Write Data (append / overwrite / merge)",
    description="Writes a dataset into an existing table. mode=append adds rows, "
                "mode=overwrite replaces all data, mode=merge upserts on merge_key.",
    tags=["Tables"],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def write_to_table(
    table_name: str,
    payload: WriteTableRequest,
    service: TableService = Depends(get_table_service),
) -> TableDetailResponse:
    """Writes data into an existing Iceberg table using append, overwrite, or merge."""
    try:
        return service.write_table(table_name=table_name, request=payload)
    except (DatasetResolutionError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (SchemaInferenceError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TableNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TableOperationError as e:
        # merge_key / mode validation errors from the manager are user errors → 400
        msg = str(e)
        if "merge_key" in msg or "Unsupported write mode" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {str(e)}")


# =============================================================================
# Table Maintenance
# =============================================================================


@router.post(
    "/v1/tables/{table_name}/compact",
    response_model=CompactResponse,
    summary="Compact Table Data Files",
    tags=["Maintenance"],
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def compact_table(
    table_name: str,
    namespace: str = Query("default"),
    catalog=Depends(get_catalog_dependency),
):
    """
    Rewrites all data files into a single consolidated Parquet file.
    Reduces file count and improves read performance.
    """
    from iceberg.maintenance import compact_table as do_compact

    try:
        result = do_compact(catalog, table_name, namespace)
        return CompactResponse(
            table_name=table_name,
            namespace=namespace,
            files_before=result.files_before,
            files_after=result.files_after,
            size_before_bytes=result.size_before_bytes,
            size_after_bytes=result.size_after_bytes,
            new_snapshot_id=result.new_snapshot_id,
        )
    except TableNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TableOperationError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/v1/tables/{table_name}/expire-snapshots",
    response_model=ExpireSnapshotsResponse,
    summary="Expire Old Snapshots",
    tags=["Maintenance"],
    responses={404: {"model": ErrorResponse}},
)
async def expire_snapshots_endpoint(
    table_name: str,
    payload: Optional[ExpireSnapshotsRequest] = None,
    namespace: str = Query("default"),
    catalog=Depends(get_catalog_dependency),
):
    """Expire snapshots older than a threshold to reclaim storage."""
    from iceberg.maintenance import expire_snapshots

    older_than_days = payload.older_than_days if payload else 30
    try:
        result = expire_snapshots(catalog, table_name, namespace, older_than_days)
        return ExpireSnapshotsResponse(
            table_name=table_name,
            namespace=namespace,
            expired_count=result.expired_count,
            remaining_count=result.remaining_count,
        )
    except TableNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TableOperationError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/v1/tables/{table_name}/snapshots",
    response_model=List[SnapshotDetailModel],
    summary="List Snapshot History",
    tags=["Maintenance"],
    responses={404: {"model": ErrorResponse}},
)
async def list_snapshots_endpoint(
    table_name: str,
    namespace: str = Query("default"),
    catalog=Depends(get_catalog_dependency),
):
    """Returns detailed snapshot history including operation type and file counts."""
    from iceberg.maintenance import list_snapshots

    try:
        snapshots = list_snapshots(catalog, table_name, namespace)
        return [
            SnapshotDetailModel(
                snapshot_id=s.snapshot_id,
                parent_snapshot_id=s.parent_snapshot_id,
                timestamp_ms=s.timestamp_ms,
                timestamp_utc=s.timestamp_utc,
                operation=s.operation,
                summary=s.summary,
                manifest_list=s.manifest_list,
            )
            for s in snapshots
        ]
    except TableNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TableOperationError as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Schema Evolution
# =============================================================================


@router.post(
    "/v1/tables/{table_name}/evolve-schema",
    response_model=SchemaEvolutionResponse,
    summary="Evolve Table Schema",
    tags=["Schema"],
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def evolve_schema(
    table_name: str,
    payload: SchemaEvolutionRequest,
    namespace: str = Query("default"),
    catalog=Depends(get_catalog_dependency),
):
    """
    Add or rename columns using Iceberg's schema evolution with stable field IDs.
    Demonstrates that existing field IDs are preserved across schema changes.
    """
    from pyiceberg.exceptions import NoSuchTableError

    identifier = (namespace.strip().lower(), table_name.strip().lower())
    try:
        table = catalog.load_table(identifier)
    except NoSuchTableError:
        raise HTTPException(status_code=404, detail=f"Table '{namespace}.{table_name}' not found.")

    if not payload.add_columns and not payload.rename_columns:
        raise HTTPException(status_code=400, detail="At least one of add_columns or rename_columns is required.")

    try:
        with table.update_schema() as update:
            if payload.add_columns:
                for col in payload.add_columns:
                    iceberg_type = _parse_type_string(col.type)
                    update.add_column(col.name, iceberg_type, doc=col.doc)
            if payload.rename_columns:
                for rename in payload.rename_columns:
                    update.rename_column(rename.from_name, rename.to_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Schema evolution failed: {str(e)}")

    # Reload table to get updated schema
    table = catalog.load_table(identifier)
    from iceberg.schema import format_schema_summary
    schema_fields = [
        FieldSchemaModel(
            field_id=f["field_id"],
            name=f["name"],
            type=f["type"],
            required=f["required"],
            doc=f.get("doc"),
        )
        for f in format_schema_summary(table.schema())
    ]

    return SchemaEvolutionResponse(
        table_name=table_name,
        namespace=namespace,
        schema_fields=schema_fields,
        message="Schema evolved successfully. Field IDs remain stable.",
    )


def _parse_type_string(type_str: str):
    """Parse a simple type string into a PyIceberg type."""
    from pyiceberg.types import (
        BooleanType, IntegerType, LongType, FloatType, DoubleType,
        StringType, DateType, TimestampType, TimestamptzType, BinaryType,
    )

    type_map = {
        "boolean": BooleanType(),
        "int": IntegerType(),
        "integer": IntegerType(),
        "long": LongType(),
        "bigint": LongType(),
        "float": FloatType(),
        "double": DoubleType(),
        "string": StringType(),
        "date": DateType(),
        "timestamp": TimestampType(),
        "timestamptz": TimestamptzType(),
        "binary": BinaryType(),
    }

    normalized = type_str.strip().lower()
    if normalized in type_map:
        return type_map[normalized]
    raise ValueError(
        f"Unsupported type '{type_str}'. Supported: {', '.join(sorted(type_map.keys()))}"
    )


# =============================================================================
# Async Job Queue
# =============================================================================


@router.post(
    "/v1/jobs/ingest",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Async Ingestion Job",
    tags=["Jobs"],
)
async def submit_ingest_job(payload: JobIngestRequest):
    """
    Submit an ingestion job for async processing.
    Returns immediately with a job_id. Poll GET /v1/jobs/{job_id} for status.
    """
    return job_service.submit_job(payload)


@router.get(
    "/v1/jobs",
    response_model=List[JobResponse],
    summary="List Jobs",
    tags=["Jobs"],
)
async def list_jobs(limit: int = Query(50, ge=1, le=200)):
    """List recent ingestion jobs with their current status."""
    return job_service.list_jobs(limit=limit)


@router.get(
    "/v1/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get Job Status",
    tags=["Jobs"],
    responses={404: {"model": ErrorResponse}},
)
async def get_job(job_id: str):
    """Poll the status of a submitted ingestion job."""
    result = job_service.get_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return result


# =============================================================================
# Query (Trino)
# =============================================================================


@router.post(
    "/v1/query",
    response_model=QueryResponse,
    summary="Execute SQL Query via Trino",
    tags=["Query"],
)
async def execute_query(payload: QueryRequest):
    """Execute a read-only SQL query against Iceberg tables via Trino."""
    try:
        service = TrinoService()
        return await service.execute_query(payload.query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
