
from __future__ import annotations

import json

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException

from notion import get_all_rows
from record import build_records
from transform import clean_frame, validate

app = FastAPI(title="Notion CRM Automation")


def records(df: pd.DataFrame) -> list[dict]:
    """pandas -> JSON-safe records: Timestamps to ISO strings, NA to null."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sync")
def sync():
    try:
        rows = get_all_rows()
    except (requests.RequestException, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Notion fetch failed: {exc}") from exc

    raw = pd.DataFrame(rows).convert_dtypes()
    clean = clean_frame(raw)
    issues = validate(clean, raw)

    return {
        "row_count": int(len(clean)),
        "issue_count": int(len(issues)),
        "Records": build_records(clean),
        "rows": records(clean),
        "issues": records(issues),
    }
