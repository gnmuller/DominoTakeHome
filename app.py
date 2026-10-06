import csv
import os

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "mock_db.csv")
MULTI = ("serums", "PARAMETERS", "initals")


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def matches(row, chosen):
    for key, value in chosen.items():
        if isinstance(value, list):
            if row[key] not in value:
                return False
        elif row[key] != value:
            return False
    return True


def options(rows, column, chosen):
    return sorted({row[column] for row in rows if matches(row, chosen)})


rows = load_rows(DB)
chosen = {}

project_choices = options(rows, "project", chosen)
if "project" in st.session_state and st.session_state["project"] not in project_choices:
    st.session_state["project"] = None
project = st.selectbox(
    "project",
    project_choices,
    index=None,
    placeholder="Select project",
    key="project",
)
if project is not None:
    chosen["project"] = project

ready = project is not None
for column in MULTI:
    choices = options(rows, column, chosen) if ready else []
    if column in st.session_state:
        kept = [value for value in st.session_state[column] if value in choices]
        if kept != list(st.session_state[column]):
            st.session_state[column] = kept
    picked = st.multiselect(
        column,
        choices,
        key=column,
        placeholder=f"Select {column}",
        disabled=not choices,
    )
    if picked:
        chosen[column] = picked
    else:
        ready = False

if len(chosen) == 1 + len(MULTI):
    match = [row for row in rows if matches(row, chosen)]
    st.dataframe(match, hide_index=True)
