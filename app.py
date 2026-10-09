import os
import re

import streamlit as st

import db

DB = db.PATH
QUARTET = ("project", "serums", "PARAMETERS", "initals")
PRIMARY = ("project", "lab", "run_date", "serums")
MULTI = ("lab", "run_date", "serums")
MORE = ("PARAMETERS", "initals", "day", "analyst", "flag", "instrument")
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
    return db.load_rows(path)


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
        if not all(
            (row.get(key) in value)
            if isinstance(value, list)
            else row.get(key) == value
            for key, value in chosen.items()
        ):
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
    assert [row["cell"] for row in matching(rows, {"project": ["P1", "P2"]})] == [
        "A1",
        "A10",
        "B1",
    ]
    assert [row["cell"] for row in matching(rows, {}, "A")] == ["A1", "A10"]
    assert [row["cell"] for row in matching(rows, {}, "A1")] == ["A1"]


def _sync(rows, column, filters):
    others = {
        key: st.session_state.get(key)
        for key in filters
        if key != column and st.session_state.get(key)
    }
    choices = options(rows, column, others)
    current = st.session_state.get(column)
    if column in MULTI and column in st.session_state:
        picked = current if isinstance(current, list) else []
        kept = [item for item in picked if item in choices]
        if kept != current:
            st.session_state[column] = kept
    elif column in st.session_state and current not in choices:
        st.session_state[column] = None
    return choices


def _dropdown(rows, column, filters):
    choices = _sync(rows, column, filters)
    label = f"Select {LABELS[column].lower()}"
    if column in MULTI:
        return st.multiselect(
            LABELS[column],
            choices,
            placeholder=label,
            key=column,
            disabled=not choices,
        )
    return st.selectbox(
        LABELS[column],
        choices,
        index=None,
        placeholder=label,
        key=column,
        disabled=not choices,
    )


_self_check()

if not os.path.isfile(DB):
    st.error(f"database file missing: {DB}")
    st.stop()

rows, columns = load_rows(DB)
missing = [LABELS[name] for name in PRIMARY if name not in columns]
if missing:
    st.error("database missing required columns: " + ", ".join(missing))
    st.stop()

filters = [name for name in PRIMARY + MORE if name in columns]
for column in PRIMARY:
    _dropdown(rows, column, PRIMARY)
if not all(st.session_state.get(column) for column in PRIMARY):
    st.write("Select project, lab, run date, and serum to view results.")
    st.stop()

more = [name for name in MORE if name in columns]
for column in more:
    _sync(rows, column, filters)
chosen = {key: st.session_state[key] for key in filters if st.session_state.get(key)}
well = st.session_state.get("well_query") or ""
match = matching(rows, chosen, well)
st.write(count_line(match, columns))
st.dataframe(display_rows(match, columns), hide_index=True)
with st.container():
    st.caption("More filters")
    for column in more:
        _dropdown(rows, column, filters)
    st.text_input("Well", key="well_query", placeholder="A7 or A")
