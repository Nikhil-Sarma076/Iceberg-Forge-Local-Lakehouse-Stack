"""
Schema Inference Tests
======================
"""

import pyarrow as pa
import pytest
from pyiceberg.types import (
    BooleanType,
    DateType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    StringType,
    TimestampType,
    TimestamptzType,
)

from iceberg.schema import (
    SchemaInferenceError,
    arrow_to_iceberg_schema,
    arrow_type_to_iceberg_type,
    infer_arrow_schema_from_file,
    read_file_to_arrow_table,
)


def test_arrow_type_mappings():
    """Verify PyArrow type mappings to PyIceberg types."""
    assert isinstance(arrow_type_to_iceberg_type(pa.string()), StringType)
    assert isinstance(arrow_type_to_iceberg_type(pa.large_string()), StringType)
    assert isinstance(arrow_type_to_iceberg_type(pa.int32()), IntegerType)
    assert isinstance(arrow_type_to_iceberg_type(pa.int64()), LongType)
    assert isinstance(arrow_type_to_iceberg_type(pa.float32()), FloatType)
    assert isinstance(arrow_type_to_iceberg_type(pa.float64()), DoubleType)
    assert isinstance(arrow_type_to_iceberg_type(pa.bool_()), BooleanType)
    assert isinstance(arrow_type_to_iceberg_type(pa.date32()), DateType)
    assert isinstance(arrow_type_to_iceberg_type(pa.timestamp("us")), TimestampType)
    assert isinstance(arrow_type_to_iceberg_type(pa.timestamp("us", tz="UTC")), TimestamptzType)


def test_csv_schema_inference(temp_test_env: dict):
    """Test reading CSV and inferring Iceberg schema."""
    arrow_table, iceberg_schema, fmt = infer_arrow_schema_from_file(temp_test_env["csv_file"])
    assert fmt == "csv"
    assert arrow_table.num_rows == 3

    field_names = [f.name for f in iceberg_schema.fields]
    assert "id" in field_names
    assert "item" in field_names
    assert "price" in field_names
    assert "is_active" in field_names


def test_json_schema_inference(temp_test_env: dict):
    """Test reading JSON and inferring Iceberg schema."""
    arrow_table, iceberg_schema, fmt = infer_arrow_schema_from_file(temp_test_env["json_file"])
    assert fmt == "json"
    assert arrow_table.num_rows == 2

    field_names = [f.name for f in iceberg_schema.fields]
    assert "event_id" in field_names
    assert "type" in field_names
    assert "duration_ms" in field_names


def test_parquet_schema_inference(temp_test_env: dict):
    """Test reading Parquet and converting schema."""
    arrow_table, iceberg_schema, fmt = infer_arrow_schema_from_file(temp_test_env["parquet_file"])
    assert fmt == "parquet"
    assert arrow_table.num_rows == 3

    field_names = [f.name for f in iceberg_schema.fields]
    assert "user_id" in field_names
    assert "username" in field_names


def test_unsupported_file_extension(tmp_path):
    """Test error when file extension is not supported."""
    fake_file = tmp_path / "data.docx"
    fake_file.write_text("dummy")

    with pytest.raises(SchemaInferenceError) as exc_info:
        read_file_to_arrow_table(fake_file)
    assert "Unsupported file format" in str(exc_info.value)
