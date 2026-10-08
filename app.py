import csv
import os
import re

import streamlit as st

DB = "/mnt/data/Worker2DatabaseProxy/mock_db.csv"
QUARTET = ("project", "serums", "PARAMETERS", "initals")
EXTRA = ("lab", "day", "analyst", "flag", "instrument", "run_date")
LABELS = {
    "project": "Project",
    "serums": "Serum",
    "PARAMETERS": "Parameter",
    "initals": "Initials",
    "cell": "Well",
    "value": "Value",
    "lab": "Lab",
    "day": "Day",
    "analyst": "Analyst",
    "flag": "Flag",
    "instrument": "Instrument",
    "run_date": "Run date",
}
_FULL_WELL = re.compile(r"[A-H](?:[1-9]|1[0-2])")


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def _well_ok(cell, text):
    text = text.strip().upper()
    if not text:
        return True
    cell = "" if cell is None else str(cell).strip().upper()
    if _FULL_WELL.fullmatch(text):
        return cell == text
    return cell.startswith(text)


def matching(rows, chosen, well=""):
    found = []
    for row in rows:
        if any(row.get(key) != value for key, value in chosen.items()):
            continue
        if _well_ok(row.get("cell", ""), well):
            found.append(row)
    return found


def options(rows, column, chosen):
    return sorted({row[column] for row in matching(rows, chosen) if row.get(column)})


def count_line(rows, columns):
    noun = "well" if len(rows) == 1 else "wells"
    line = f"{len(rows)} {noun}"
    if not rows:
        return line
    plates = {tuple(row.get(key, "") for key in QUARTET) for row in rows}
    if len(plates) != 1:
        return line
    identity = [value for value in plates.pop() if value]
    for key in ("lab", "day"):
        if key not in columns:
            continue
        identity.extend(sorted({row.get(key, "") for row in rows if row.get(key)}))
    return line + " · " + ", ".join(identity)


def display_rows(rows, columns):
    return [{LABELS.get(key, key): row.get(key, "") for key in columns} for row in rows]


def _self_check():
    rows = [
        {"project": "P1", "cell": "A1"},
        {"project": "P1", "cell": "A10"},
        {"project": "P2", "cell": "B1"},
    ]
    assert matching(rows, {}) == rows
    assert matching(rows, {"project": "P1"}) == rows[:2]
    assert [row["cell"] for row in matching(rows, {}, "A")] == ["A1", "A10"]
    assert [row["cell"] for row in matching(rows, {}, "A1")] == ["A1"]


def _dropdown(rows, column, filters):
    others = {
        key: st.session_state.get(key)
        for key in filters
        if key != column and st.session_state.get(key)
    }
    choices = options(rows, column, others)
    if column in st.session_state and st.session_state[column] not in choices:
        st.session_state[column] = None
    return st.selectbox(
        LABELS[column],
        choices,
        index=None,
        placeholder=f"Select {LABELS[column].lower()}",
        key=column,
        disabled=not choices,
    )


_self_check()

if not os.path.isfile(DB):
    st.error(f"database file missing: {DB}")
    st.stop()
else:
    rows, columns = load_rows(DB)
    filters = [name for name in QUARTET + EXTRA if name in columns]
    chosen = {}
    for column in [name for name in QUARTET if name in filters]:
        value = _dropdown(rows, column, filters)
        if value:
            chosen[column] = value
    well = st.text_input("Well", key="well_query", placeholder="A7 or A")
    for column in [name for name in EXTRA if name in filters]:
        value = _dropdown(rows, column, filters)
        if value:
            chosen[column] = value

    match = matching(rows, chosen, well)
    st.write(count_line(match, columns))
    st.dataframe(display_rows(match, columns), hide_index=True)
