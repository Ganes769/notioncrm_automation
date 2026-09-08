import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_API_BASE_URL = os.getenv("NOTION_API_BASE_URL", "https://api.notion.com/v1").rstrip("/")
NOTION_VERSION = os.getenv("NOTION_VERSION", "2025-09-03")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

if not NOTION_TOKEN:
    raise RuntimeError("NOTION_TOKEN is missing. Add it to .env")
if not NOTION_DATABASE_ID:
    raise RuntimeError("NOTION_DATABASE_ID is missing. Add it to .env")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def get_data_source_id(database_id: str) -> str:
    url = f"{NOTION_API_BASE_URL}/databases/{database_id}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data_sources = response.json().get("data_sources", [])
    if not data_sources:
        raise RuntimeError(f"Database {database_id} has no data sources.")

    data_source_id = data_sources[0]["id"]
    print(f"[notion] database {database_id}")
    print(f"[notion]   resolves to data source {data_source_id}  <- what /query needs")
    return data_source_id


def get_database_rows(data_source_id: str) -> list[dict]:
    url = f"{NOTION_API_BASE_URL}/data_sources/{data_source_id}/query"
    rows = []
    start_cursor = None
    page = 0

    while True:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])
        rows.extend(results)

        page += 1
        print(f"[notion] page {page}: {len(results)} rows, has_more={data.get('has_more')}")

        start_cursor = data.get("next_cursor")
        if not data.get("has_more") or not start_cursor:
            break

    return rows


def property_value(prop: dict):
    kind = prop["type"]
    data = prop.get(kind)

    if data is None:
        return None
    if kind in ("title", "rich_text"):
        text = "".join(part.get("plain_text", "") for part in data)
        return text or None
    if kind == "select":
        return data.get("name")
    if kind == "multi_select":
        return [option["name"] for option in data]
    if kind == "status":
        return data.get("name")
    if kind == "date":
        return data.get("start")
    if kind == "people":
        return [person.get("name") or person.get("id") for person in data]
    if kind == "files":
        return [
            file.get("name") or file.get("file", {}).get("url") or file.get("external", {}).get("url")
            for file in data
        ]
    if kind == "relation":
        return [item["id"] for item in data]
    if kind in ("formula", "unique_id"):
        return property_value(data) if isinstance(data, dict) and "type" in data else data
    if kind == "rollup":
        return data.get("array") or data.get("number") or data.get("date")

    return data


def to_plain_row(page: dict) -> dict:
    return {name: property_value(prop) for name, prop in page.get("properties", {}).items()}


def get_all_rows(database_id: str | None = None) -> list[dict]:
    database_id = database_id or NOTION_DATABASE_ID
    if not database_id:
     raise ValueError("NOTION_DATABASE_ID is required")
    data_source_id = get_data_source_id(database_id)
    pages = get_database_rows(data_source_id)
    rows = [to_plain_row(page) for page in pages]

    if pages:
        # One page before and after flattening: Notion's nesting is the surprise here.
        print("[notion] raw JSON for the first row:")
        print(json.dumps(pages[0], indent=2))
        print("[notion] same row after flattening:")
        print(json.dumps(rows[0], indent=2, default=str))

    print(f"[notion] returned {len(rows)} flat rows with {len(rows[0]) if rows else 0} fields each")
    return rows