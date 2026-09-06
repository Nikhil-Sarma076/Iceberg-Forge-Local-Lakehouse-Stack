"""
Table Management Integration Tests
==================================
"""

from fastapi.testclient import TestClient


def test_create_and_describe_csv_table(client: TestClient, temp_test_env: dict):
    """Test creating an Iceberg table from CSV and retrieving its description."""
    table_name = "test_sales_tbl"
    csv_file = temp_test_env["csv_file"]

    # 1. Create table
    create_res = client.post(
        "/v1/tables",
        json={"name": table_name, "file": csv_file},
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == table_name
    assert created_data["total_records"] == 3
    assert len(created_data["schema_fields"]) == 4
    assert created_data["current_snapshot_id"] is not None

    # 2. Describe table
    get_res = client.get(f"/v1/tables/{table_name}")
    assert get_res.status_code == 200
    detail_data = get_res.json()
    assert detail_data["name"] == table_name
    assert detail_data["total_records"] == 3
    assert len(detail_data["snapshots"]) >= 1

    # 3. Duplicate creation conflict (409)
    dup_res = client.post(
        "/v1/tables",
        json={"name": table_name, "file": csv_file},
    )
    assert dup_res.status_code == 409


def test_list_tables(client: TestClient, temp_test_env: dict):
    """Test listing all tables in default namespace."""
    table_name = "test_events_tbl"
    json_file = temp_test_env["json_file"]

    # Create table
    client.post("/v1/tables", json={"name": table_name, "file": json_file})

    # List tables
    list_res = client.get("/v1/tables")
    assert list_res.status_code == 200
    tables = list_res.json()
    assert isinstance(tables, list)
    table_names = [t["name"] for t in tables]
    assert table_name in table_names


def test_append_data_to_table(client: TestClient, temp_test_env: dict):
    """Test appending additional records to an existing Iceberg table."""
    table_name = "test_append_tbl"
    csv_file = temp_test_env["csv_file"]
    append_file = temp_test_env["append_csv"]

    # 1. Create initial table (3 records)
    client.post("/v1/tables", json={"name": table_name, "file": csv_file})

    # 2. Append 2 more records
    append_res = client.post(
        f"/v1/tables/{table_name}/append",
        json={"file": append_file},
    )
    assert append_res.status_code == 200
    appended_data = append_res.json()
    assert appended_data["total_records"] == 5
    assert len(appended_data["snapshots"]) == 2


def test_delete_table(client: TestClient, temp_test_env: dict):
    """Test deleting an Iceberg table."""
    table_name = "test_delete_tbl"
    json_file = temp_test_env["json_file"]

    # Create table
    client.post("/v1/tables", json={"name": table_name, "file": json_file})

    # Delete table
    del_res = client.delete(f"/v1/tables/{table_name}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm 404 on subsequent get
    get_res = client.get(f"/v1/tables/{table_name}")
    assert get_res.status_code == 404


# --- Merge / upsert logic ---

import pyarrow as pa
from iceberg.tables import IcebergTableManager


class _FakeScan:
    def __init__(self, table): self._t = table
    def to_arrow(self): return self._t


class _FakeTable:
    """Minimal stand-in exposing scan().to_arrow() for _merge_arrow."""
    def __init__(self, arrow_table): self._t = arrow_table
    def scan(self): return _FakeScan(self._t)


def test_merge_arrow_upserts_without_duplicates():
    """
    Merge must REPLACE rows whose key matches an incoming row (not append a
    duplicate) while keeping non-matching existing rows and adding brand-new keys.

    Regression guard: a prior bug concatenated the *unfiltered* existing table
    with incoming, so matching keys were kept AND re-added, producing duplicates.
    """
    existing = pa.table({
        "id": [1, 2, 3],
        "name": ["a", "b", "c"],
    })
    # id=2 overlaps (should be updated), id=99 is new (should be added), id=1,3 kept.
    incoming = pa.table({
        "id": [2, 99],
        "name": ["b_updated", "new"],
    })

    merged = IcebergTableManager._merge_arrow(_FakeTable(existing), incoming, "id")

    ids = merged.column("id").to_pylist()
    assert sorted(ids) == [1, 2, 3, 99]           # 4 rows, no duplicate id=2
    assert len(ids) == len(set(ids))              # no duplicate keys

    by_id = {r["id"]: r["name"] for r in merged.to_pylist()}
    assert by_id[2] == "b_updated"                # matching row replaced, not duplicated
    assert by_id[1] == "a" and by_id[3] == "c"    # non-matching rows retained
    assert by_id[99] == "new"                     # brand-new key added


def test_merge_arrow_into_empty_table_returns_incoming():
    """Merging into an empty table yields exactly the incoming rows."""
    existing = pa.table({"id": pa.array([], type=pa.int64()), "name": pa.array([], type=pa.string())})
    incoming = pa.table({"id": [1, 2], "name": ["x", "y"]})
    merged = IcebergTableManager._merge_arrow(_FakeTable(existing), incoming, "id")
    assert merged.num_rows == 2
    assert sorted(merged.column("id").to_pylist()) == [1, 2]
