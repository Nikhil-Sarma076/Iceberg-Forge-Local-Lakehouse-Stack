"""
Pytest Fixtures & Configuration
===============================
Provides isolated SQLite-based Iceberg catalog, sample files, and FastAPI TestClient.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
import pytest
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pa_parquet
from fastapi.testclient import TestClient
from pyiceberg.catalog import Catalog, load_catalog

from app.api.dependencies import get_catalog_dependency, get_ingestion_service, get_settings
from app.config.settings import Settings
from app.main import app
from app.services.ingestion_service import IngestionService
from iceberg.tables import IcebergTableManager


@pytest.fixture(scope="session")
def temp_test_env() -> Generator[dict, None, None]:
    """Creates a temporary isolated warehouse directory and SQLite catalog DB."""
    temp_dir = tempfile.mkdtemp(prefix="iceberg_test_")
    warehouse_path = os.path.join(temp_dir, "warehouse")
    os.makedirs(warehouse_path, exist_ok=True)
    db_path = os.path.join(temp_dir, "catalog.db")

    sample_dir = os.path.join(temp_dir, "sample-data")
    os.makedirs(sample_dir, exist_ok=True)

    # 1. Create sample CSV
    csv_file = os.path.join(sample_dir, "test_sales.csv")
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("id,item,price,is_active\n")
        f.write("1,Widget,25.50,true\n")
        f.write("2,Gadget,99.00,false\n")
        f.write("3,Doohickey,12.99,true\n")

    # 2. Create sample JSON
    json_file = os.path.join(sample_dir, "test_events.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump([
            {"event_id": "e1", "type": "click", "duration_ms": 45.2, "flag": True},
            {"event_id": "e2", "type": "scroll", "duration_ms": 12.0, "flag": False},
        ], f)

    # 3. Create sample Parquet
    parquet_file = os.path.join(sample_dir, "test_users.parquet")
    arrow_table = pa.table({
        "user_id": [101, 102, 103],
        "username": ["alice", "bob", "carol"],
        "score": [98.5, 87.0, 92.3],
        "is_verified": [True, False, True],
    })
    pa_parquet.write_table(arrow_table, parquet_file)

    # 4. Create sample append CSV
    append_csv = os.path.join(sample_dir, "test_sales_append.csv")
    with open(append_csv, "w", encoding="utf-8") as f:
        f.write("id,item,price,is_active\n")
        f.write("4,Thingamajig,55.00,true\n")
        f.write("5,Gizmo,150.00,false\n")

    env_data = {
        "temp_dir": temp_dir,
        "warehouse": warehouse_path,
        "db_path": db_path,
        "sample_dir": sample_dir,
        "csv_file": csv_file,
        "json_file": json_file,
        "parquet_file": parquet_file,
        "append_csv": append_csv,
    }

    yield env_data

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_catalog(temp_test_env: dict) -> Catalog:
    """Provides an isolated REST Catalog backed by memory and local file warehouse."""
    uri = f"sqlite:///{temp_test_env['db_path']}"
    warehouse = f"file://{temp_test_env['warehouse']}"

    properties = {
        "type": "sql",
        "uri": uri,
        "warehouse": warehouse,
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    catalog = load_catalog("test_catalog", **properties)
    return catalog


@pytest.fixture
def test_table_manager(test_catalog: Catalog) -> IcebergTableManager:
    return IcebergTableManager(catalog=test_catalog)


@pytest.fixture
def client(temp_test_env: dict, test_catalog: Catalog) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden dependencies for testing."""
    test_settings = Settings(
        SAMPLE_DATA_DIR=temp_test_env["sample_dir"],
        ICEBERG_WAREHOUSE=f"file://{temp_test_env['warehouse']}",
        ICEBERG_CATALOG_URI=f"sqlite:///{temp_test_env['db_path']}",
    )
    test_ingestion = IngestionService(sample_data_dir=temp_test_env["sample_dir"])

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_catalog_dependency] = lambda: test_catalog
    app.dependency_overrides[get_ingestion_service] = lambda: test_ingestion

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
