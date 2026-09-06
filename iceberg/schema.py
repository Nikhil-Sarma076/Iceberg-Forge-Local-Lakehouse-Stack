"""
Schema Inference and Type Translation
=====================================
Transforms PyArrow schemas into Apache Iceberg schemas.
Supports CSV, JSON, and Parquet source files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.json as pa_json
import pyarrow.parquet as pa_parquet

from pyiceberg.schema import Schema
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IcebergType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
    TimestamptzType,
)


class SchemaInferenceError(Exception):
    """Raised when schema inference or conversion fails."""
    pass


def arrow_type_to_iceberg_type(arrow_type: pa.DataType) -> IcebergType:
    """
    Map a PyArrow data type to the corresponding PyIceberg data type.

    Supported PyArrow types:
    - String / LargeString -> StringType
    - Int8, Int16, Int32, UInt8, UInt16 -> IntegerType
    - Int64, UInt32, UInt64 -> LongType
    - Float16, Float32 -> FloatType
    - Float64 -> DoubleType
    - Boolean -> BooleanType
    - Date32, Date64 -> DateType
    - Timestamp (with/without tz) -> TimestamptzType / TimestampType
    - Binary / LargeBinary -> BinaryType
    - Decimal128, Decimal256 -> DecimalType
    """
    if pa.types.is_boolean(arrow_type):
        return BooleanType()

    if pa.types.is_int8(arrow_type) or pa.types.is_int16(arrow_type) or pa.types.is_int32(arrow_type) or pa.types.is_uint8(arrow_type) or pa.types.is_uint16(arrow_type):
        return IntegerType()

    if pa.types.is_int64(arrow_type) or pa.types.is_uint32(arrow_type) or pa.types.is_uint64(arrow_type):
        return LongType()

    if pa.types.is_float16(arrow_type) or pa.types.is_float32(arrow_type):
        return FloatType()

    if pa.types.is_float64(arrow_type):
        return DoubleType()

    if pa.types.is_date32(arrow_type) or pa.types.is_date64(arrow_type):
        return DateType()

    if pa.types.is_timestamp(arrow_type):
        if arrow_type.tz is not None and str(arrow_type.tz).strip() != "":
            return TimestamptzType()
        return TimestampType()

    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return StringType()

    if pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
        return BinaryType()

    if pa.types.is_decimal(arrow_type):
        return DecimalType(precision=arrow_type.precision, scale=arrow_type.scale)

    # Fallback for null or unknown types
    if pa.types.is_null(arrow_type):
        return StringType()

    # Struct and list types are flattened before reaching here,
    # but if encountered, store as JSON string
    if pa.types.is_struct(arrow_type) or pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type) or pa.types.is_map(arrow_type):
        return StringType()

    # Default fallback to string to prevent ingestion failure on esoteric types
    return StringType()


def arrow_to_iceberg_schema(arrow_schema: pa.Schema) -> Schema:
    """
    Convert a PyArrow Schema into an Apache Iceberg Schema.
    Assigns sequential field IDs starting from 1.
    """
    fields: List[NestedField] = []
    for idx, field in enumerate(arrow_schema, start=1):
        iceberg_type = arrow_type_to_iceberg_type(field.type)
        # In Iceberg, fields are optional unless explicitly required
        is_required = not field.nullable
        fields.append(
            NestedField(
                field_id=idx,
                name=field.name,
                field_type=iceberg_type,
                required=is_required,
                doc=f"Inferred from PyArrow field '{field.name}'",
            )
        )
    return Schema(*fields)


def flatten_arrow_table(table: pa.Table) -> pa.Table:
    """
    Flatten an Arrow table by expanding struct columns into dot-notation
    and converting list/array columns to JSON string representation.

    Example:
        address: struct<city: string, state: string>
        → address.city: string, address.state: string

        skills: list<string>
        → skills: string (JSON serialized, e.g. '["Python","SQL"]')
    """
    import json as _json

    flat_columns = []
    flat_names = []

    for i, field in enumerate(table.schema):
        col = table.column(i)

        if pa.types.is_struct(field.type):
            # Recursively flatten struct fields with dot-notation prefix
            _flatten_struct(col, field.name, field.type, flat_columns, flat_names)
        elif pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
            # Convert list column to JSON strings
            json_strings = [_json.dumps(val.as_py()) if val.is_valid else None for val in col]
            flat_columns.append(pa.array(json_strings, type=pa.string()))
            flat_names.append(field.name)
        elif pa.types.is_map(field.type):
            # Convert map column to JSON strings
            json_strings = [_json.dumps(val.as_py()) if val.is_valid else None for val in col]
            flat_columns.append(pa.array(json_strings, type=pa.string()))
            flat_names.append(field.name)
        else:
            flat_columns.append(col)
            flat_names.append(field.name)

    return pa.table(flat_columns, names=flat_names)


def _flatten_struct(
    col: pa.ChunkedArray,
    prefix: str,
    struct_type: pa.StructType,
    out_columns: list,
    out_names: list,
) -> None:
    """Recursively flatten a struct column into its child fields."""
    import json as _json

    for j in range(struct_type.num_fields):
        child_field = struct_type.field(j)
        child_name = f"{prefix}.{child_field.name}"

        # Extract the child column from each chunk
        child_arrays = []
        for chunk in col.chunks:
            child_arrays.append(chunk.field(j))
        child_col = pa.chunked_array(child_arrays)

        if pa.types.is_struct(child_field.type):
            _flatten_struct(child_col, child_name, child_field.type, out_columns, out_names)
        elif pa.types.is_list(child_field.type) or pa.types.is_large_list(child_field.type):
            json_strings = [_json.dumps(val.as_py()) if val.is_valid else None for val in child_col]
            out_columns.append(pa.array(json_strings, type=pa.string()))
            out_names.append(child_name)
        else:
            out_columns.append(child_col)
            out_names.append(child_name)


# Default cap on rows read purely to infer column data types (e.g. for the
# create-table schema preview). Full ingestion ignores this.
SAMPLE_ROW_LIMIT = 2000


def normalize_column_names(table: pa.Table) -> pa.Table:
    """
    Normalize Arrow table column names by replacing spaces and special chars with underscores.
    This prevents encoding issues in PyIceberg (e.g., 'Customer Id' → 'Customer_Id').
    """
    new_columns = []
    new_names = []
    for field, col in zip(table.schema, table.columns):
        # Replace spaces with underscores
        normalized_name = field.name.replace(' ', '_')
        new_names.append(normalized_name)
        new_columns.append(col)
    
    return pa.table(new_columns, names=new_names)


def read_file_to_arrow_table(
    file_path: Union[str, Path],
    sample_rows: Optional[int] = None,
) -> Tuple[pa.Table, str]:
    """
    Detects file format and reads the file into a PyArrow Table.

    Supports:
    - CSV (.csv)
    - JSON (.json, .jsonl, .ndjson - standard array or newline-delimited)
    - Parquet (.parquet, .pq)

    Args:
        file_path: Path to the source file.
        sample_rows: If set, read at most this many rows. Used for fast schema /
            type inference (the create-table preview) so we do not load a
            multi-million row file just to detect column types. When None, the
            full file is read (used for actual ingestion).

    Returns:
        Tuple of (PyArrow Table, detected_format_string)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()

    try:
        if suffix in [".csv", ".txt"]:
            # Configure CSV parse options to infer date/timestamp strings where possible
            convert_options = pa_csv.ConvertOptions(
                strings_can_be_null=True,
                auto_dict_encode=False,
            )
            if sample_rows and sample_rows > 0:
                # Stream batches and stop once we have enough rows for type inference.
                reader = pa_csv.open_csv(path, convert_options=convert_options)
                batches = []
                collected = 0
                for batch in reader:
                    batches.append(batch)
                    collected += batch.num_rows
                    if collected >= sample_rows:
                        break
                if batches:
                    table = pa.Table.from_batches(batches).slice(0, sample_rows)
                else:
                    table = pa_csv.read_csv(path, convert_options=convert_options).slice(0, 0)
            else:
                table = pa_csv.read_csv(path, convert_options=convert_options)
            # Normalize column names (replace spaces with underscores)
            table = normalize_column_names(table)
            return table, "csv"

        elif suffix in [".json", ".jsonl", ".ndjson"]:
            table = _read_json(path, sample_rows)
            # Flatten nested structs/lists into flat columns for Iceberg compatibility
            table = flatten_arrow_table(table)
            if sample_rows and sample_rows > 0:
                table = table.slice(0, sample_rows)
            # Normalize column names
            table = normalize_column_names(table)
            return table, "json"

        elif suffix in [".parquet", ".pq"]:
            if sample_rows and sample_rows > 0:
                # Parquet stores schema in metadata; read only enough rows to sample.
                pf = pa_parquet.ParquetFile(path)
                batch = next(pf.iter_batches(batch_size=sample_rows), None)
                table = pa.Table.from_batches([batch]) if batch is not None else pf.read().slice(0, 0)
            else:
                table = pa_parquet.read_table(path)
            # Normalize column names
            table = normalize_column_names(table)
            return table, "parquet"

        else:
            raise SchemaInferenceError(
                f"Unsupported file format '{suffix}'. Supported formats: .csv, .json, .parquet"
            )

    except Exception as e:
        if isinstance(e, (FileNotFoundError, SchemaInferenceError)):
            raise
        raise SchemaInferenceError(f"Failed to read and parse file '{path.name}': {str(e)}") from e


def _read_json(path: Path, sample_rows: Optional[int]) -> pa.Table:
    """
    Read a JSON file into an Arrow table, optionally capping rows for sampling.

    PyArrow's JSON reader has no native row limit, so when sampling we read only
    the first N lines of a newline-delimited file. Standard (array) JSON is parsed
    then sliced — best effort, since the whole array must be parsed first.
    """
    if sample_rows and sample_rows > 0:
        # Try newline-delimited first: read only the first N lines cheaply.
        try:
            import io
            lines: List[str] = []
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= sample_rows:
                        break
                    if line.strip():
                        lines.append(line)
            if lines:
                buf = io.BytesIO("".join(lines).encode("utf-8"))
                return pa_json.read_json(buf)
        except Exception:
            pass  # fall through to full parse + slice

    try:
        return pa_json.read_json(path)
    except Exception:
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            if sample_rows and sample_rows > 0:
                data = data[:sample_rows]
            return pa.Table.from_pylist(data)
        elif isinstance(data, dict):
            return pa.Table.from_pylist([data])
        else:
            raise ValueError("JSON file must contain an object or array of objects.")


def infer_arrow_schema_from_file(
    file_path: Union[str, Path],
    sample_rows: Optional[int] = None,
) -> Tuple[pa.Table, Schema, str]:
    """
    Reads a file into a PyArrow table and computes its Iceberg schema.

    Args:
        file_path: Path to the source file.
        sample_rows: When set, only this many rows are read to infer types
            (used by the preview endpoint). None reads the full file.

    Returns:
        Tuple of (PyArrow Table, PyIceberg Schema, format_name)
    """
    arrow_table, file_format = read_file_to_arrow_table(file_path, sample_rows=sample_rows)
    iceberg_schema = arrow_to_iceberg_schema(arrow_table.schema)
    return arrow_table, iceberg_schema, file_format


def format_schema_summary(schema: Schema) -> List[Dict[str, Any]]:
    """
    Format PyIceberg schema fields into a clean dictionary list for API responses.
    """
    summary = []
    for field in schema.fields:
        summary.append({
            "field_id": field.field_id,
            "name": field.name,
            "type": str(field.field_type),
            "required": field.required,
            "doc": field.doc,
        })
    return summary
