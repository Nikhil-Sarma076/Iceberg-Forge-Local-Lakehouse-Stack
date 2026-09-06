.PHONY: help up down restart logs test test-cov ingest-sample trino-cli clean

help:
	@echo "Local Iceberg Ingestion Toolkit - Available Commands:"
	@echo "  make up             - Build and start all services (MinIO, FastAPI, Trino)"
	@echo "  make down           - Stop and remove all containers"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - Stream container logs"
	@echo "  make test           - Run automated tests in test container/local environment"
	@echo "  make test-cov       - Run tests with code coverage"
	@echo "  make ingest-sample  - Ingest sample datasets (sales.csv, events.json, products.csv)"
	@echo "  make trino-cli      - Open interactive Trino CLI connected to Iceberg catalog"
	@echo "  make clean          - Remove containers, volumes, and temporary files"

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov=iceberg --cov-report=term-missing

ingest-sample:
	@echo "Ingesting sales.csv..."
	@curl -s -X POST http://localhost:8000/v1/tables \
		-H "Content-Type: application/json" \
		-d '{"name": "sales", "file": "sales.csv"}' | python3 -m json.tool || true
	@echo "\nIngesting events.json..."
	@curl -s -X POST http://localhost:8000/v1/tables \
		-H "Content-Type: application/json" \
		-d '{"name": "events", "file": "events.json"}' | python3 -m json.tool || true
	@echo "\nIngesting products.csv..."
	@curl -s -X POST http://localhost:8000/v1/tables \
		-H "Content-Type: application/json" \
		-d '{"name": "products", "file": "products.csv"}' | python3 -m json.tool || true

trino-cli:
	docker exec -it iceberg-trino trino --catalog iceberg --schema default

clean:
	docker compose down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov
