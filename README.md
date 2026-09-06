# Local Iceberg Ingestion Toolkit

> A lightweight, production-quality Python service that converts CSV, JSON, and Parquet datasets into Apache Iceberg tables backed by MinIO object storage, queryable instantly via Trino.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PyIceberg](https://img.shields.io/badge/Apache_Iceberg-PyIceberg_0.6+-blue.svg?logo=apache)](https://py.iceberg.apache.org/)
[![PyArrow](https://img.shields.io/badge/PyArrow-15.0+-orange.svg)](https://arrow.apache.org/)
[![MinIO](https://img.shields.io/badge/MinIO-S3_Compatible-c72c48.svg?logo=minio&logoColor=white)](https://min.io/)
[![Trino](https://img.shields.io/badge/Trino-SQL_Query_Engine-DD00A1.svg?logo=trino&logoColor=white)](https://trino.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [The Problem It Solves](#the-problem-it-solves)
3. [Architecture](#architecture)
4. [Supported Formats & Schema Inference](#supported-formats--schema-inference)
5. [Quick Start](#quick-start)
6. [Core API Reference & Examples](#core-api-reference--examples)
7. [Async Job Queue](#async-job-queue)
8. [Partition Support](#partition-support)
9. [Table Maintenance](#table-maintenance)
10. [Schema Evolution](#schema-evolution)
11. [Querying with Trino](#querying-with-trino)
12. [Demo Pipeline](#demo-pipeline)
13. [Testing](#testing)
14. [Repository Structure](#repository-structure)
15. [Design Decisions](#design-decisions)
16. [Known Limitations](#known-limitations)

---

## Project Overview

**Local Iceberg Ingestion Toolkit** is an open-source demonstration project designed to showcase practical Python backend data engineering and lakehouse integration. It provides a clean REST API interface to validate ad-hoc datasets, infer strict column typing using PyArrow, construct Apache Iceberg tables using PyIceberg, persist metadata and Parquet data files into MinIO S3 object storage, and expose the tables for distributed SQL querying via Trino.

---

## The Problem It Solves

Modern data architectures are converging on open table formats like **Apache Iceberg** to eliminate vendor lock-in, enable ACID transactions on data lakes, and decouple compute engines from object storage. However:

- Setting up an Iceberg environment locally often requires heavyweight Spark clusters or JVM dependencies.
- Ingesting raw CSV/JSON/Parquet files into an Iceberg table typically requires multi-step manual schema definition and complex boilerplate.
- Small engineering teams and data practitioners need a lightweight, Python-native micro-toolkit to test table creation, schema evolution, and query workflows locally before rolling out enterprise lakehouse pipelines.

This toolkit bridges that gap with a zero-JVM Python ingestion runtime and Docker Compose integration.

---

## Architecture

```
                                  INGESTION WORKFLOW
                                  
  ┌─────────────────┐
  │ CSV/JSON/Parquet│
  │   Source File   │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ FastAPI Service (Local Ingestion Toolkit)                   │
  │                                                             │
  │   1. Path & Filename Validation (Pydantic)                  │
  │   2. Fast Columnar Parsing (PyArrow)                        │
  │   3. Schema Detection & Type Mapping (schema.py)            │
  │   4. Catalog Metadata Registration (catalog.py)             │
  │   5. Snapshot Creation & Data Append (tables.py)            │
  └────────┬────────────────────────────────────────────────────┘
           │
           ├──────────────────────────────┐
           ▼ (Parquet Files & Metadata)   ▼ (Table Pointer / SQLite DB)
  ┌─────────────────┐           ┌──────────────────┐
  │ MinIO (S3)      │           │ Iceberg Catalog  │
  │ Storage Bucket  │           │ SQLite Metadata  │
  │ iceberg-warehse │           │ (Shared Volume)  │
  └────────┬────────┘           └─────────┬────────┘
           │                              │
           └──────────────┬───────────────┘
                          │
                          ▼
               ┌──────────────────────┐
               │ Trino Query Engine   │
               │ (Distributed SQL)    │
               │ SELECT * FROM table  │
               └──────────────────────┘
```

### End-to-End Ingestion Flow

1. **Client Request**: Client submits `POST /v1/tables` with `{"name": "sales", "file": "sales.csv"}`.
2. **File Resolution**: `IngestionService` validates that the file exists and is readable.
3. **PyArrow Parsing**: The file format is auto-detected (`.csv`, `.json`, `.parquet`), and parsed into an in-memory columnar `pyarrow.Table`.
4. **Schema Translation**: `iceberg/schema.py` inspects the PyArrow types and translates them to exact `pyiceberg.schema.Schema` fields with deterministic field IDs.
5. **Iceberg Catalog Registration**: `IcebergTableManager` uses PyIceberg to create the table in the configured SQLite-backed Iceberg catalog.
6. **Data Commit**: PyIceberg writes partitioned/unpartitioned Parquet files and commits an Iceberg snapshot to MinIO S3 (`s3://iceberg-warehouse/warehouse/default/sales/...`).
7. **Trino Availability**: Trino's Iceberg connector reads the commit metadata from MinIO and catalog DB, making the table queryable in real-time.

---

## Supported Formats & Schema Inference

The toolkit supports automated schema inference across three primary data formats:

| Format | Extension | Parser | Notes |
| :--- | :--- | :--- | :--- |
| **CSV** | `.csv`, `.txt` | `pyarrow.csv` | Headers inferred, type auto-detection for numbers, booleans, dates |
| **JSON** | `.json`, `.jsonl`, `.ndjson` | `pyarrow.json` / stdlib fallback | Supports newline-delimited JSON and standard JSON arrays |
| **Parquet** | `.parquet`, `.pq` | `pyarrow.parquet` | Native columnar schema preservation and fast metadata reading |

### PyArrow to Iceberg Type Mapping

| PyArrow Type | PyIceberg Type | SQL / Trino Equivalent |
| :--- | :--- | :--- |
| `pa.string()`, `pa.large_string()` | `StringType()` | `VARCHAR` |
| `pa.int8()`, `pa.int16()`, `pa.int32()` | `IntegerType()` | `INTEGER` |
| `pa.int64()`, `pa.uint32()`, `pa.uint64()` | `LongType()` | `BIGINT` |
| `pa.float16()`, `pa.float32()` | `FloatType()` | `REAL` |
| `pa.float64()` | `DoubleType()` | `DOUBLE` |
| `pa.bool_()` | `BooleanType()` | `BOOLEAN` |
| `pa.date32()`, `pa.date64()` | `DateType()` | `DATE` |
| `pa.timestamp(unit, tz=None)` | `TimestampType()` | `TIMESTAMP` |
| `pa.timestamp(unit, tz="UTC")` | `TimestamptzType()` | `TIMESTAMP WITH TIME ZONE` |
| `pa.binary()`, `pa.large_binary()` | `BinaryType()` | `VARBINARY` |
| `pa.decimal128(p, s)` | `DecimalType(p, s)` | `DECIMAL(p, s)` |

### Column Name Normalization

**Important**: Column names containing spaces (e.g., `"Customer Id"`, `"First Name"`) are automatically normalized by replacing spaces with underscores (e.g., `"Customer_Id"`, `"First_Name"`). This ensures compatibility with PyIceberg's field name encoding and prevents schema validation errors during merge operations.

**Example**:
- Input CSV: `Customer Id, First Name, Last Name`
- Table schema: `Customer_Id: string, First_Name: string, Last_Name: string`
- Trino query: `SELECT Customer_Id, First_Name FROM iceberg.default.customers`

When using merge operations, specify the merge key with spaces as it appears in the original file—the normalization is applied automatically:
```bash
curl -X POST http://localhost:8000/v1/tables/customers/write \
  -H "Content-Type: application/json" \
  -d '{"file": "customers.csv", "mode": "merge", "merge_key": "Customer Id"}'
```

This normalization is applied automatically to all file formats (CSV, JSON, Parquet) at read time.

---

## Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)
- `curl` (or Postman/HTTPie)

### 1. Launch the Stack

```bash
docker compose up --build -d
```

Verify services are healthy:
- **FastAPI API**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **MinIO Console**: [http://localhost:9001](http://localhost:9001) (`admin` / `password123`)
- **Trino Web UI**: [http://localhost:8080](http://localhost:8080)
# Access UIs
- **React UI**: [http://localhost:3001](http://localhost:3001)


### 2. Ingest Sample Datasets

Run the pre-configured Makefile target:

```bash
make ingest-sample
```

Or make direct API calls:

```bash
# Ingest Sales CSV
curl -X POST http://localhost:8000/v1/tables \
  -H "Content-Type: application/json" \
  -d '{"name": "sales", "file": "sales.csv"}'

# Ingest Events JSON
curl -X POST http://localhost:8000/v1/tables \
  -H "Content-Type: application/json" \
  -d '{"name": "events", "file": "events.json"}'

# Ingest Products CSV
curl -X POST http://localhost:8000/v1/tables \
  -H "Content-Type: application/json" \
  -d '{"name": "products", "file": "products.csv"}'
```

---

## Core API Reference & Examples

### `GET /health`
Verifies service health.

**Response (`200 OK`)**:
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `POST /v1/tables`
Creates an Iceberg table from a local dataset. Optionally partition using Iceberg transforms.

**Request Body**:
```json
{
  "name": "sales",
  "file": "sales.csv",
  "namespace": "default",
  "partition_by": ["days(order_date)", "identity(region)"]
}
```

**Response (`201 Created`)**:
```json
{
  "name": "sales",
  "namespace": "default",
  "identifier": "default.sales",
  "location": "s3://iceberg-warehouse/warehouse/default/sales",
  "format_version": 2,
  "current_snapshot_id": 4829104928172910382,
  "total_records": 8,
  "total_files": 1,
  "total_data_size_bytes": 2840,
  "schema_fields": [
    {
      "field_id": 1,
      "name": "order_id",
      "type": "long",
      "required": false,
      "doc": "Inferred from PyArrow field 'order_id'"
    },
    {
      "field_id": 2,
      "name": "customer_id",
      "type": "string",
      "required": false,
      "doc": "Inferred from PyArrow field 'customer_id'"
    },
    {
      "field_id": 3,
      "name": "product_category",
      "type": "string",
      "required": false,
      "doc": "Inferred from PyArrow field 'product_category'"
    },
    {
      "field_id": 4,
      "name": "amount",
      "type": "double",
      "required": false,
      "doc": "Inferred from PyArrow field 'amount'"
    },
    {
      "field_id": 5,
      "name": "is_discounted",
      "type": "boolean",
      "required": false,
      "doc": "Inferred from PyArrow field 'is_discounted'"
    }
  ],
  "partition_spec": [],
  "properties": {
    "write.format.default": "parquet",
    "created_by": "local-iceberg-ingestion-toolkit"
  },
  "snapshots": [
    {
      "snapshot_id": 4829104928172910382,
      "parent_snapshot_id": null,
      "timestamp_ms": 1705318400000,
      "operation": "append",
      "summary": {
        "operation": "append",
        "added-data-files": "1",
        "added-records": "8",
        "total-records": "8"
      }
    }
  ],
  "inferred_from_file": "/app/sample-data/sales.csv",
  "detected_format": "csv"
}
```

---

### `GET /v1/tables`
Lists metadata summaries for all registered tables.

**Response (`200 OK`)**:
```json
[
  {
    "name": "sales",
    "namespace": "default",
    "identifier": "default.sales",
    "location": "s3://iceberg-warehouse/warehouse/default/sales",
    "total_records": 8,
    "current_snapshot_id": 4829104928172910382,
    "schema_fields_count": 7
  },
  {
    "name": "events",
    "namespace": "default",
    "identifier": "default.events",
    "location": "s3://iceberg-warehouse/warehouse/default/events",
    "total_records": 5,
    "current_snapshot_id": 8920194829102847291,
    "schema_fields_count": 7
  }
]
```

---

### `GET /v1/tables/{table_name}`
Retrieves detailed schema, snapshot history, and file statistics.

**Example**: `GET /v1/tables/sales`

---

### `POST /v1/tables/{table_name}/append`
Appends additional records to an existing Iceberg table.

**Request Body**:
```json
{
  "file": "orders_append.csv"
}
```

**Response (`200 OK`)**:
```json
{
  "name": "sales",
  "total_records": 11,
  "total_files": 2,
  "snapshots": [
    {
      "snapshot_id": 4829104928172910382,
      "operation": "append"
    },
    {
      "snapshot_id": 9182740192837461928,
      "parent_snapshot_id": 4829104928172910382,
      "operation": "append"
    }
  ]
}
```

---

### `DELETE /v1/tables/{table_name}`
Drops the table from the Iceberg catalog.

**Response (`200 OK`)**:
```json
{
  "status": "deleted",
  "identifier": "default.sales",
  "message": "Table 'default.sales' was successfully removed from the catalog."
}
```

---

## Async Job Queue

The async job queue provides a production-style **submit → queue → execute → poll** pattern for ingestion tasks. Jobs are processed by a background worker, allowing the API to return immediately.

### `POST /v1/jobs/ingest`
Submit an async ingestion job. Returns immediately with a job ID.

**Request Body**:
```json
{
  "name": "events",
  "file": "events.json",
  "namespace": "default",
  "partition_by": ["days(event_time)"]
}
```

**Response (`202 Accepted`)**:
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "QUEUED",
  "message": "Job queued for processing."
}
```

### `GET /v1/jobs/{job_id}`
Poll job status until `COMPLETED` or `FAILED`.

**Response**:
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "COMPLETED",
  "created_at": "2024-01-15T10:30:00+00:00",
  "started_at": "2024-01-15T10:30:01+00:00",
  "completed_at": "2024-01-15T10:30:03+00:00",
  "request": {"name": "events", "file": "events.json", "namespace": "default"},
  "result": { "...full TableDetailResponse..." },
  "error": null
}
```

### `GET /v1/jobs`
List recent jobs with current status (newest first).

---

## Partition Support

Tables can now be created with partition transforms via the `partition_by` field on both `POST /v1/tables` and `POST /v1/jobs/ingest`.

### Supported Transforms

| Transform | Example | Description |
|-----------|---------|-------------|
| `identity(col)` | `identity(region)` | Partition by raw column value |
| `years(col)` | `years(created_at)` | Extract year from timestamp/date |
| `months(col)` | `months(created_at)` | Extract month |
| `days(col)` | `days(event_time)` | Extract day |
| `hours(col)` | `hours(event_time)` | Extract hour |
| `bucket(n, col)` | `bucket(16, user_id)` | Hash-bucket into n partitions |
| `truncate(n, col)` | `truncate(3, zip_code)` | Truncate to width n |

### Example: Partitioned Table Creation

```bash
curl -X POST http://localhost:8000/v1/tables \
  -H "Content-Type: application/json" \
  -d '{
    "name": "events",
    "file": "events.json",
    "partition_by": ["days(event_time)", "identity(region)"]
  }'
```

---

## Table Maintenance

### `POST /v1/tables/{table_name}/compact`
Rewrites all data files into a single consolidated Parquet file, reducing file count and improving read performance.

**Response**:
```json
{
  "table_name": "sales",
  "namespace": "default",
  "files_before": 4,
  "files_after": 1,
  "size_before_bytes": 12840,
  "size_after_bytes": 3200,
  "new_snapshot_id": 7291038471920384
}
```

### `POST /v1/tables/{table_name}/expire-snapshots`
Expire old snapshots to reclaim storage.

**Request Body** (optional):
```json
{
  "older_than_days": 7
}
```

**Response**:
```json
{
  "table_name": "sales",
  "namespace": "default",
  "expired_count": 3,
  "remaining_count": 2
}
```

### `GET /v1/tables/{table_name}/snapshots`
Returns detailed snapshot history with timestamps, operations, and file counts.

**Response**:
```json
[
  {
    "snapshot_id": 4829104928172910382,
    "parent_snapshot_id": null,
    "timestamp_ms": 1705318400000,
    "timestamp_utc": "2024-01-15T12:00:00+00:00",
    "operation": "append",
    "summary": {"added-data-files": "1", "total-records": "8"},
    "manifest_list": "s3://iceberg-warehouse/..."
  }
]
```

---

## Schema Evolution

### `POST /v1/tables/{table_name}/evolve-schema`
Add or rename columns using Iceberg's schema evolution. Field IDs remain stable across changes, ensuring backward compatibility.

**Request Body**:
```json
{
  "add_columns": [
    {"name": "discount_pct", "type": "double"},
    {"name": "notes", "type": "string", "doc": "Order notes"}
  ],
  "rename_columns": [
    {"from": "old_name", "to": "new_name"}
  ]
}
```

**Supported types**: `boolean`, `int`, `integer`, `long`, `bigint`, `float`, `double`, `string`, `date`, `timestamp`, `timestamptz`, `binary`

**Response**:
```json
{
  "table_name": "sales",
  "namespace": "default",
  "schema_fields": [
    {"field_id": 1, "name": "order_id", "type": "long", "required": false},
    {"field_id": 2, "name": "customer_id", "type": "string", "required": false},
    {"field_id": 6, "name": "discount_pct", "type": "double", "required": false}
  ],
  "message": "Schema evolved successfully. Field IDs remain stable."
}
```

---

## Querying with Trino

Once ingested, query the Iceberg table using the API's query endpoint, Trino CLI, or any SQL client.

### `POST /v1/query`
Execute read-only SQL queries against Iceberg tables via Trino without leaving the API.

**Request Body**:
```json
{
  "query": "SELECT product_category, COUNT(*) as cnt FROM iceberg.default.sales GROUP BY 1"
}
```

**Response**:
```json
{
  "columns": ["product_category", "cnt"],
  "rows": [["Electronics", 3], ["Clothing", 5]],
  "row_count": 2
}
```

> Only `SELECT` queries are permitted. DDL/DML statements are rejected.

### Trino CLI

```bash
docker exec -it iceberg-trino trino --catalog iceberg --schema default
```

### 2. Run SQL Queries

```sql
-- Show available tables
SHOW TABLES;

-- Query sales data
SELECT 
    product_category,
    COUNT(*) as total_orders,
    ROUND(SUM(amount), 2) as total_revenue,
    ROUND(AVG(amount), 2) as avg_order_value
FROM sales
GROUP BY product_category
ORDER BY total_revenue DESC;

-- Inspect Iceberg Table Metadata / Snapshots via Trino System Tables
SELECT 
    committed_at,
    snapshot_id,
    parent_id,
    operation,
    summary['total-records'] AS total_records
FROM "sales$snapshots";

-- Time travel query (query historical snapshot)
SELECT * FROM sales FOR VERSION AS OF 4829104928172910382;
```

---

## Demo Pipeline

A full end-to-end demo script exercises all major features against the running Docker stack:

```bash
# Start the stack
docker compose up --build -d

# Wait ~10s for services to initialize, then run the demo
./scripts/demo_pipeline.sh
```

The script performs 11 steps in sequence:

1. Health check
2. Create table (synchronous)
3. Append data
4. Schema evolution (add column)
5. List snapshots
6. Compact data files
7. Expire old snapshots
8. Async job submission with partition spec + poll until complete
9. List jobs
10. Query via Trino
11. Cleanup (delete demo tables)

Each step prints a colored pass/fail indicator. If any step fails, the script exits immediately with the error.

---

## Testing

### Unit Tests (no Docker required)

The partition parser has pure unit tests that run without any infrastructure:

```bash
pytest tests/test_new_features.py::TestPartitionParser -v
```

### Integration Tests (requires PyIceberg + local SQLite catalog)

```bash
pytest tests/ -v
```

Test coverage includes:
- **Existing**: health check, schema inference, table CRUD, validation
- **New features**: partition parser (10 tests), job queue endpoints (4), partition API (3), schema evolution (5), table maintenance (5)

Total: **27 new tests** across all new features.

---

## Repository Structure

```
local-iceberg-ingestion/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py    # FastAPI dependency injection (Catalog, Service singletons)
│   │   └── routes.py          # REST endpoint handlers & HTTP status mappings
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py        # Centralized Pydantic Settings from environment
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py             # Async job queue request/response models
│   │   └── table.py           # Pydantic request/response schemas & validation
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ingestion_service.py # Dataset resolution & PyArrow loading
│   │   ├── job_service.py     # In-memory async job queue & background worker
│   │   ├── table_service.py   # High-level orchestration & business logic
│   │   └── trino_service.py   # Trino query execution via HTTP
│   ├── __init__.py
│   └── main.py                # FastAPI application entry point & lifespan worker
├── iceberg/
│   ├── __init__.py
│   ├── catalog.py             # PyIceberg Catalog factory with MinIO / S3 config
│   ├── maintenance.py         # Compaction, snapshot expiration, snapshot listing
│   ├── partition.py           # Partition transform string parser → PartitionSpec
│   ├── schema.py              # PyArrow to PyIceberg schema inference & type system
│   └── tables.py              # Low-level PyIceberg table lifecycle & snapshots
├── sample-data/
│   ├── sales.csv              # Retail transactions sample dataset
│   ├── events.json            # Web analytics event logs sample dataset
│   ├── products.csv           # Product catalog sample dataset
│   └── orders_append.csv      # Incremental batch dataset for append verification
├── scripts/
│   └── demo_pipeline.sh       # End-to-end feature demo (runs against Docker stack)
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Isolated SQLite PyIceberg catalog & TestClient fixtures
│   ├── test_health.py         # System health check tests
│   ├── test_new_features.py   # Partition, jobs, evolution, maintenance tests (27 tests)
│   ├── test_schema.py         # Type translation & format inference unit tests
│   ├── test_validation.py     # Table name & input validation tests
│   └── test_tables.py         # Table CRUD & append integration tests
├── .gitignore
├── docker-compose.yml         # Multi-container orchestration (MinIO + FastAPI + Trino)
├── Dockerfile                 # Minimal Python 3.11 image with Uvicorn
├── Makefile                   # Developer automation tasks
├── requirements.txt           # Python dependency manifest
└── README.md                  # Project documentation
```

---

## Design Decisions

### 1. Why Apache Iceberg?
Apache Iceberg provides a modern table format that brings ACID transactions, hidden partitioning, schema evolution with full ID stability, and snapshot isolation to data lakes. Unlike Hive-style directories, Iceberg tracks data files through metadata trees (manifest lists and manifest files), enabling sub-second query planning and snapshot rollbacks.

### 2. Why PyIceberg?
PyIceberg is the official Python implementation of the Apache Iceberg table spec. It enables purely Python-native metadata manipulation, schema definition, and file-level data writing without requiring a running JVM or PySpark cluster. This dramatically reduces memory footprint, container startup latency, and development complexity for ingestion services.

### 3. Why MinIO?
MinIO provides a high-performance, S3-API-compatible object storage server that runs effortlessly in local Docker containers. It replicates AWS S3 behavior, headers, and multipart upload semantics, ensuring that code tested locally against MinIO functions identically against production S3 or GCS buckets without code modification.

### 4. Why Trino?
Trino (formerly PrestoSQL) is the industry standard distributed SQL query engine for data lakehouses. Trino's native Iceberg connector directly reads Iceberg metadata trees and queries MinIO-stored Parquet files with zero query translation overhead, proving out realistic multi-engine interoperability.

### 5. Why FastAPI?
FastAPI offers asynchronous execution, automatic OpenAPI schema generation, strict type enforcement via Pydantic, and fast JSON serialization. It provides self-documenting interactive Swagger UI (`/docs`) and fast startup times.

### 6. Why Schema Inference?
Ad-hoc datasets (CSVs, JSON extracts) frequently lack formal data definitions. By leveraging PyArrow's C++ type inference engine, we derive precise data types (integers, doubles, timestamps, dates) and map them to standard Iceberg types before table creation. This prevents string-only schemas and maintains strict column type safety.

### 7. Why Separate API, Service, and Iceberg Layers?
The codebase separates HTTP transport concerns (`app/api`), orchestration workflows (`app/services`), and low-level table format specifications (`iceberg/`). This decoupling ensures that:
- PyIceberg operations can be unit tested without starting FastAPI.
- Ingestion strategies can be changed (e.g., adding streaming or S3 pre-signed URLs) without altering catalog logic.
- The catalog backends (SQLite, REST, Glue, Nessie) can be swapped via configuration without touching API endpoints.

---

## Known Limitations

- **Single-Node SQLite Catalog**: The local Docker Compose setup uses an Iceberg REST catalog backed by SQLite. In production, use a distributed catalog (Polaris, Nessie, AWS Glue) for multi-writer concurrency.
- **In-Memory Arrow Parsing**: Datasets are loaded into PyArrow tables in memory. For multi-gigabyte files, chunked streaming ingestion should be implemented.
- **In-Memory Job Queue**: Jobs are stored in a Python dict and processed by a single asyncio worker. State is lost on restart. Upgrade path: Redis or SQS-backed queue.
- **Naive Compaction**: The compaction endpoint reads all data into memory and rewrites as a single file. Production systems use Spark's `rewriteDataFiles` with bin-packing for TB-scale tables.
- **Naive Merge**: The merge (upsert) operation reads the entire existing table into memory for copy-on-write comparison. Ceiling is O(table_size) RAM. Production upgrade path: Spark `MERGE INTO` or Iceberg row-level deletes (merge-on-read) for TB-scale datasets.

---

## License

MIT License. Designed and crafted for educational and portfolio demonstration.
