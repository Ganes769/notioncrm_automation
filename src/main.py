import pandas as pd

from notion import get_all_rows
from transform import clean_frame, validate

rows = get_all_rows()
raw = pd.DataFrame(rows).convert_dtypes()

clean = clean_frame(raw)
issues = validate(clean, raw)

print(f"{len(clean)} rows, {len(issues)} issues\n")
print(clean[["source_id", "account", "contact", "work_email", "employees", "segment"]], "\n")
print(issues.to_string(index=False))