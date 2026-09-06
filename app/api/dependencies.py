"""
API Dependencies
================
Provides reusable dependency injection for FastAPI route handlers.
"""

from functools import lru_cache
from fastapi import Depends
from pyiceberg.catalog import Catalog

from app.config.settings import Settings, settings
from app.services.ingestion_service import IngestionService
from app.services.table_service import TableService
from iceberg.catalog import get_iceberg_catalog
from iceberg.tables import IcebergTableManager


@lru_cache()
def get_settings() -> Settings:
    """Returns singleton application settings."""
    return settings


@lru_cache()
def get_catalog_dependency() -> Catalog:
    """Returns singleton Iceberg catalog instance."""
    return get_iceberg_catalog()


def get_table_manager(
    catalog: Catalog = Depends(get_catalog_dependency),
) -> IcebergTableManager:
    """Provides IcebergTableManager instance."""
    return IcebergTableManager(catalog=catalog)


def get_ingestion_service(
    app_settings: Settings = Depends(get_settings),
) -> IngestionService:
    """Provides IngestionService configured with sample data directory."""
    return IngestionService(sample_data_dir=app_settings.SAMPLE_DATA_DIR)


def get_table_service(
    table_manager: IcebergTableManager = Depends(get_table_manager),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> TableService:
    """Provides TableService combining table manager and ingestion logic."""
    return TableService(
        table_manager=table_manager,
        ingestion_service=ingestion_service,
    )
