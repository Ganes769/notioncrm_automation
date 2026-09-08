
from __future__ import annotations

import json
import time

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
    started = time.perf_counter()
    print("[api] /sync starting")

    try:
        rows = get_all_rows()
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[api] /sync failed at the Notion fetch: {exc}")
        raise HTTPException(status_code=502, detail=f"Notion fetch failed: {exc}") from exc

    raw = pd.DataFrame(rows).convert_dtypes()
    clean = clean_frame(raw)
    issues = validate(clean, raw)
    payload = build_records(clean)

    print(
        f"[api] /sync done in {time.perf_counter() - started:.2f}s: "
        f"{len(clean)} rows, {len(issues)} issues, "
        f"{len(payload['company'])} companies, {len(payload['people'])} people"
    )

    return {
        "row_count": int(len(clean)),
        "issue_count": int(len(issues)),
        "Records": payload,
        "rows": records(clean),
        "issues": records(issues),
    }
