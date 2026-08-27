"""Build the Records payload (company + people) from cleaned Notion rows."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from notion import get_all_rows
from transform import clean_frame

OUT_FILE = Path(__file__).resolve().parent.parent / "out" / "records.json"


def domain_of(url) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    text = url.strip()
    host = urlsplit(text if "://" in text else f"https://{text}").netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _text(value):
    """pandas NA -> None, so JSON gets null instead of the string '<NA>'."""
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def company_records(clean: pd.DataFrame) -> list[dict]:
    rows = clean.copy()
    rows["domain"] = rows["website"].map(domain_of)
    rows = rows.dropna(subset=["domain"]).drop_duplicates(subset=["domain"], keep="first")

    out = []
    for row in rows.itertuples(index=False):
        segment = _text(row.segment)
        out.append(
            {
                "domain": _text(row.domain),
                "name": _text(row.account),
                "description": _text(row.research_notes),
                "team": _text(row.employees),
                "categories": [segment] if segment else [],
                "owner": _text(row.owner),
                "hq": _text(row.hq),
            }
        )
    return out


def people_records(clean: pd.DataFrame) -> list[dict]:
    out = []
    for row in clean.itertuples(index=False):
        out.append(
            {
                "source_id": _text(row.source_id),
                "first_name": _text(row.first_name),
                "last_name": _text(row.last_name),
                "full_name": _text(row.contact),
                "email": _text(row.work_email),
                "job_title": _text(row.job_title),
                "linkedin": _text(row.linkedin),
                "company_domain": domain_of(_text(row.website)),
                "lead_source": _text(row.lead_source),
                "owner": _text(row.owner),
            }
        )
    return out


def build_records(clean: pd.DataFrame) -> dict:
    return {
        "company": company_records(clean),
        "people": people_records(clean),
    }


def build_from_notion() -> dict:
    raw = pd.DataFrame(get_all_rows()).convert_dtypes()
    return build_records(clean_frame(raw))


if __name__ == "__main__":
    payload = {"Records": build_from_notion()}

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2))

    print(f"company : {len(payload['Records']['company'])}")
    print(f"people  : {len(payload['Records']['people'])}")
    print(f"written : {OUT_FILE}")