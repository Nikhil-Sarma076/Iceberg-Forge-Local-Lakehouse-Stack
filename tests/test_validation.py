"""
Request Validation Tests
========================
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.table import CreateTableRequest


def test_valid_table_names():
    """Verify standard table naming validation."""
    valid_names = ["sales", "orders_2024", "raw_events_v1", "user_metrics"]
    for name in valid_names:
        req = CreateTableRequest(name=name, file="sales.csv")
        assert req.name == name.lower()


def test_invalid_table_names():
    """Verify invalid table names raise validation errors."""
    invalid_names = [
        "",                     # empty
        "123_numbers",          # starts with digit
        "sales-data",           # contains hyphen
        "sales table",          # contains space
        "sales;drop table x;",  # SQL injection attempt
        "a" * 65,               # too long
    ]
    for name in invalid_names:
        with pytest.raises(ValidationError):
            CreateTableRequest(name=name, file="sales.csv")


def test_file_not_found_endpoint(client: TestClient):
    """Verifies that non-existent input file returns 404."""
    response = client.post(
        "/v1/tables",
        json={"name": "non_existent_test", "file": "does_not_exist_99.csv"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_invalid_payload_fields(client: TestClient):
    """Verifies 422 Unprocessable Entity for malformed body."""
    response = client.post(
        "/v1/tables",
        json={"wrong_field": "test"},
    )
    assert response.status_code == 422
