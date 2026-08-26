# src/clean.py
"""Basic cleaning and validation for Notion CRM rows."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from notion import get_all_rows

EMPLOYEE_BUCKETS = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001+"]
SEGMENTS = ["SMB", "Mid-market", "Enterprise"]
CRM_STATUSES = ["Ready for CRM", "In CRM", "On hold", "Disqualified"]

SOURCE_ID_RE = re.compile(r"^QL-\d{6}-\d{3}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Notion CSV imports mix Unicode dashes with plain hyphens.
_DASHES = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-", 0x2212: "-"}



def clean_text(value):
    """Unify dashes, collapse whitespace, blank -> None. Non-strings -> None."""
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value).translate(_DASHES)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_name(value):
    text = clean_text(value)
    if not text:
        return None
    return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))


def clean_email(value):
    text = clean_text(value)
    return text.lower().strip(".,;") if text else None


def clean_employees(value):
    """'11 – 50' and '11-50' both become '11-50'."""
    text = clean_text(value)
    if not text:
        return None
    return re.sub(r"\s*-\s*", "-", text.replace(",", ""))


# --- Cleaning ---------------------------------------------------------------

def clean_frame(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)

    out["source_id"] = raw["Source ID"].map(clean_text).astype("string")
    out["account"] = raw["Account"].map(clean_name).astype("string")
    out["contact"] = raw["Contact"].map(clean_name).astype("string")
    out["hq"] = raw["HQ"].map(clean_name).astype("string")

    out["job_title"] = raw["Job title"].map(clean_text).astype("string")
    out["lead_source"] = raw["Lead source"].map(clean_text).astype("string")
    out["research_notes"] = raw["Research notes"].map(clean_text).astype("string")
    out["website"] = raw["Website"].map(clean_text).astype("string")
    out["linkedin"] = raw["LinkedIn"].map(clean_text).astype("string")

    out["work_email"] = raw["Work email"].map(clean_email).astype("string")
    out["employees"] = raw["Employees"].map(clean_employees).astype("string")
    out["segment"] = raw["Segment"].map(clean_text).astype("string")
    out["crm_status"] = raw["CRM status"].map(clean_text).astype("string")
    out["owner"] = raw["Owner"].map(clean_name).astype("string")

    out["qualified_on"] = pd.to_datetime(raw["Qualified on"], errors="coerce")

    names = out["contact"].str.split(" ", n=1, expand=True)
    out["first_name"] = names[0].astype("string")
    out["last_name"] = (names[1] if names.shape[1] > 1 else pd.NA)
    out["last_name"] = out["last_name"].astype("string")

    return out



def validate(clean: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    issues: list[dict] = []

    def flag(mask, field, problem):
        for i in clean.index[mask.fillna(False)]:
            issues.append(
                {
                    "row": i,
                    "source_id": clean.at[i, "source_id"],
                    "field": field,
                    "problem": problem,
                    "value": clean.at[i, field] if field in clean else None,
                }
            )

    # Required
    for field in ("source_id", "account", "contact", "qualified_on"):
        flag(clean[field].isna(), field, "missing")

    # Source ID format and uniqueness
    flag(
        clean["source_id"].notna() & ~clean["source_id"].str.match(SOURCE_ID_RE),
        "source_id",
        "expected QL-YYMMDD-NNN",
    )
    flag(clean["source_id"].duplicated(keep=False), "source_id", "duplicate")

    # Name casing was corrected during cleaning
    flag(raw["Contact"].ne(clean["contact"]), "contact", "name case/spacing fixed")
    flag(raw["Account"].ne(clean["account"]), "account", "name case/spacing fixed")

    # Contact should have first and last name
    flag(clean["last_name"].isna() & clean["contact"].notna(), "contact", "no last name")

    # Email
    flag(clean["work_email"].isna(), "work_email", "missing")
    flag(
        clean["work_email"].notna() & ~clean["work_email"].str.match(EMAIL_RE),
        "work_email",
        "invalid format",
    )
    flag(
        clean["work_email"].notna() & clean["work_email"].duplicated(keep=False),
        "work_email",
        "duplicate email",
    )
    flag(raw["Work email"].ne(clean["work_email"]), "work_email", "case/spacing fixed")

    # Controlled values
    flag(
        clean["employees"].notna() & ~clean["employees"].isin(EMPLOYEE_BUCKETS),
        "employees",
        f"not in {EMPLOYEE_BUCKETS}",
    )
    flag(clean["segment"].notna() & ~clean["segment"].isin(SEGMENTS), "segment", f"not in {SEGMENTS}")
    flag(
        clean["crm_status"].notna() & ~clean["crm_status"].isin(CRM_STATUSES),
        "crm_status",
        f"not in {CRM_STATUSES}",
    )
    flag(raw["Employees"].ne(clean["employees"]), "employees", "dash/spacing fixed")

    # Dates
    flag(clean["qualified_on"] > pd.Timestamp.today().normalize(), "qualified_on", "future date")

    columns = ["row", "source_id", "field", "problem", "value"]
    if not issues:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(issues).sort_values(["row", "field"], ignore_index=True)


def run():
    raw = pd.DataFrame(get_all_rows()).convert_dtypes()
    clean = clean_frame(raw)
    issues = validate(clean, raw)
    return clean, issues


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    clean, issues = run()

    print(f"{len(clean)} rows, {len(issues)} issues\n")
    print(clean[["source_id", "account", "contact", "work_email", "employees", "segment"]], "\n")
    print(issues.to_string(index=False))