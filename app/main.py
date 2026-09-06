"""
Local Iceberg Ingestion Toolkit - FastAPI Application
=====================================================
Entry point for the REST API service.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background workers on startup, clean up on shutdown."""
    from app.api.dependencies import get_catalog_dependency, get_settings
    from app.services.ingestion_service import IngestionService
    from app.services.job_service import start_worker
    from app.services.table_service import TableService
    from iceberg.tables import IcebergTableManager

    app_settings = get_settings()
    catalog = get_catalog_dependency()
    table_manager = IcebergTableManager(catalog=catalog)
    ingestion_service = IngestionService(sample_data_dir=app_settings.SAMPLE_DATA_DIR)
    table_service = TableService(table_manager=table_manager, ingestion_service=ingestion_service)
    start_worker(table_service)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-quality local service that ingests CSV, JSON, and Parquet datasets "
        "into Apache Iceberg tables backed by MinIO object storage with Trino query support."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for local experimentation & tooling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router)


@app.get("/", tags=["System"])
async def root_overview():
    """Service overview & navigation index."""
    return JSONResponse(
        content={
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "online",
            "docs": "/docs",
            "endpoints": {
                "health": "/health",
                "create_table": "POST /v1/tables",
                "list_tables": "GET /v1/tables",
                "describe_table": "GET /v1/tables/{table_name}",
                "delete_table": "DELETE /v1/tables/{table_name}",
                "append_table": "POST /v1/tables/{table_name}/append",
                "compact_table": "POST /v1/tables/{table_name}/compact",
                "expire_snapshots": "POST /v1/tables/{table_name}/expire-snapshots",
                "list_snapshots": "GET /v1/tables/{table_name}/snapshots",
                "evolve_schema": "POST /v1/tables/{table_name}/evolve-schema",
                "submit_job": "POST /v1/jobs/ingest",
                "list_jobs": "GET /v1/jobs",
                "get_job": "GET /v1/jobs/{job_id}",
                "query": "POST /v1/query",
            },
            "warehouse": settings.ICEBERG_WAREHOUSE,
            "catalog_type": settings.ICEBERG_CATALOG_TYPE,
        }
    )
