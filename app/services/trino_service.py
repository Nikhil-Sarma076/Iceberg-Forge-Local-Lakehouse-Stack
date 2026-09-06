import httpx
import asyncio
from app.config.settings import settings

TRINO_ENDPOINT = f"http://{settings.TRINO_HOST}:{settings.TRINO_PORT}"

class TrinoService:
    async def execute_query(self, query: str):
        query_upper = query.strip().upper()
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "MERGE"]
        if any(query_upper.startswith(keyword) for keyword in forbidden):
            raise ValueError("Only read-only (SELECT) queries are allowed.")
            
        headers = {"X-Trino-User": "fastapi-client"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{TRINO_ENDPOINT}/v1/statement", data=query.encode('utf-8'), headers=headers)
            if response.status_code != 200:
                raise Exception(f"Trino query failed: {response.text}")
                
            data = response.json()
            next_uri = data.get("nextUri")
            columns = data.get("columns", [])
            rows = data.get("data", [])
            
            while next_uri:
                await asyncio.sleep(0.5)
                res = await client.get(next_uri)
                if res.status_code != 200:
                    raise Exception(f"Trino fetch failed: {res.text}")
                data = res.json()
                
                if "error" in data:
                    raise Exception(data["error"]["message"])
                    
                if "columns" in data and not columns:
                    columns = data["columns"]
                    
                if "data" in data:
                    rows.extend(data["data"])
                    
                next_uri = data.get("nextUri")
                
            return {
                "columns": [c["name"] for c in columns] if columns else [],
                "rows": rows,
                "row_count": len(rows)
            }
