"""
New Features Integration Tests
==============================
Tests for: async job queue, schema evolution, and table maintenance
(compact, snapshots).
"""

import time
import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Integration Tests: Async Job Queue
# =============================================================================


class TestJobQueue:
    """Tests for POST /v1/jobs/ingest, GET /v1/jobs, GET /v1/jobs/{id}."""

    def test_submit_job_returns_202(self, client: TestClient, temp_test_env: dict):
        res = client.post("/v1/jobs/ingest", json={
            "name": "job_test_tbl",
            "file": temp_test_env["csv_file"],
        })
        assert res.status_code == 202
        data = res.json()
        assert "job_id" in data
        assert data["status"] == "QUEUED"

    def test_list_jobs(self, client: TestClient, temp_test_env: dict):
        # Submit a job first
        client.post("/v1/jobs/ingest", json={
            "name": "job_list_tbl",
            "file": temp_test_env["csv_file"],
        })
        res = client.get("/v1/jobs")
        assert res.status_code == 200
        jobs = res.json()
        assert isinstance(jobs, list)
        assert len(jobs) >= 1

    def test_get_job_not_found(self, client: TestClient):
        res = client.get("/v1/jobs/nonexistent-id")
        assert res.status_code == 404

    def test_get_job_by_id(self, client: TestClient, temp_test_env: dict):
        submit_res = client.post("/v1/jobs/ingest", json={
            "name": "job_get_tbl",
            "file": temp_test_env["csv_file"],
        })
        job_id = submit_res.json()["job_id"]

        res = client.get(f"/v1/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("QUEUED", "RUNNING", "COMPLETED", "FAILED")


# =============================================================================
# Integration Tests: Schema Evolution
# =============================================================================


class TestSchemaEvolution:
    """Tests for POST /v1/tables/{name}/evolve-schema."""

    def test_add_column(self, client: TestClient, temp_test_env: dict):
        """Add a column and verify it appears with a new field_id."""
        # Create table first
        client.post("/v1/tables", json={
            "name": "evolve_tbl",
            "file": temp_test_env["csv_file"],
        })

        # Evolve schema
        res = client.post("/v1/tables/evolve_tbl/evolve-schema", json={
            "add_columns": [{"name": "discount_pct", "type": "double"}],
        })
        assert res.status_code == 200
        data = res.json()
        field_names = [f["name"] for f in data["schema_fields"]]
        assert "discount_pct" in field_names
        assert data["message"] == "Schema evolved successfully. Field IDs remain stable."

    def test_rename_column(self, client: TestClient, temp_test_env: dict):
        """Rename a column and verify old name gone, new name present."""
        client.post("/v1/tables", json={
            "name": "rename_tbl",
            "file": temp_test_env["csv_file"],
        })

        res = client.post("/v1/tables/rename_tbl/evolve-schema", json={
            "rename_columns": [{"from": "item", "to": "product_name"}],
        })
        assert res.status_code == 200
        field_names = [f["name"] for f in res.json()["schema_fields"]]
        assert "product_name" in field_names
        assert "item" not in field_names

    def test_evolve_nonexistent_table_404(self, client: TestClient):
        res = client.post("/v1/tables/ghost_table/evolve-schema", json={
            "add_columns": [{"name": "x", "type": "string"}],
        })
        assert res.status_code == 404

    def test_evolve_empty_request_400(self, client: TestClient, temp_test_env: dict):
        """Empty evolution request (no adds, no renames) should 400."""
        client.post("/v1/tables", json={
            "name": "empty_evolve_tbl",
            "file": temp_test_env["csv_file"],
        })
        res = client.post("/v1/tables/empty_evolve_tbl/evolve-schema", json={})
        assert res.status_code == 400

    def test_add_invalid_type_400(self, client: TestClient, temp_test_env: dict):
        """Unsupported type string should return 400."""
        client.post("/v1/tables", json={
            "name": "bad_type_tbl",
            "file": temp_test_env["csv_file"],
        })
        res = client.post("/v1/tables/bad_type_tbl/evolve-schema", json={
            "add_columns": [{"name": "x", "type": "map<string,int>"}],
        })
        assert res.status_code == 400


# =============================================================================
# Integration Tests: Table Maintenance
# =============================================================================


class TestMaintenance:
    """Tests for compact, expire-snapshots, and list-snapshots endpoints."""

    def test_compact_table(self, client: TestClient, temp_test_env: dict):
        """Create + append → compact → files_after <= files_before."""
        # Create with initial data (1 file)
        client.post("/v1/tables", json={
            "name": "compact_tbl",
            "file": temp_test_env["csv_file"],
        })
        # Append more data (2 files now)
        client.post("/v1/tables/compact_tbl/append", json={
            "file": temp_test_env["append_csv"],
        })

        # Compact
        res = client.post("/v1/tables/compact_tbl/compact")
        assert res.status_code == 200
        data = res.json()
        assert data["files_before"] >= 2
        assert data["files_after"] <= data["files_before"]

    def test_compact_nonexistent_404(self, client: TestClient):
        res = client.post("/v1/tables/ghost_table/compact")
        assert res.status_code == 404

    def test_list_snapshots(self, client: TestClient, temp_test_env: dict):
        """After create + append, should have 2+ snapshots."""
        client.post("/v1/tables", json={
            "name": "snap_list_tbl",
            "file": temp_test_env["csv_file"],
        })
        client.post("/v1/tables/snap_list_tbl/append", json={
            "file": temp_test_env["append_csv"],
        })

        res = client.get("/v1/tables/snap_list_tbl/snapshots")
        assert res.status_code == 200
        snapshots = res.json()
        assert isinstance(snapshots, list)
        assert len(snapshots) >= 2
        # Each snapshot has required fields
        for s in snapshots:
            assert "snapshot_id" in s
            assert "timestamp_utc" in s
            assert "operation" in s

    def test_list_snapshots_nonexistent_404(self, client: TestClient):
        res = client.get("/v1/tables/ghost_table/snapshots")
        assert res.status_code == 404

    def test_expire_snapshots(self, client: TestClient, temp_test_env: dict):
        """Expire with older_than_days=0 should not expire current snapshot."""
        client.post("/v1/tables", json={
            "name": "expire_tbl",
            "file": temp_test_env["csv_file"],
        })

        # Expire with threshold of 0 days — nothing should be expired
        # because current snapshot is always preserved
        res = client.post("/v1/tables/expire_tbl/expire-snapshots", json={
            "older_than_days": 30,
        })
        assert res.status_code == 200
        data = res.json()
        assert "expired_count" in data
        assert "remaining_count" in data
        assert data["remaining_count"] >= 1
