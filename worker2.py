import csv
import os
import sys
from datetime import datetime

from openpyxl import load_workbook

from worker1 import (
    INITIALS,
    N_COLS,
    PARAMETERS,
    PROJECTS,
    ROWS,
    SERUMS,
    build_workbook,
)

RAW = "/mnt/data/Worker1Raw"
DB = "/mnt/data/Worker2DatabaseProxy"
artifacts_logs = "/mnt/artifacts/logs"


def plate_rows(ws):
    fields = (
        ("A1", "project", PROJECTS, ws["A1"].value),
        ("A2", "serum", SERUMS, ws["A2"].value),
        ("A3", "parameter", PARAMETERS, ws["A3"].value),
        ("A4", "initials", INITIALS, ws["A4"].value),
    )
    for cell, label, allowed, value in fields:
        if value not in allowed:
            raise ValueError(f'skipped: {cell} {label} not allowed: "{value}"')
    project, serum, parameter, initials = (item[3] for item in fields)
    rows = []
    for r, letter in enumerate(ROWS):
        got = ws.cell(row=5 + r, column=1).value
        if got != letter:
            raise ValueError(f"skipped: row {letter} label is {got!r}")
        for c in range(1, N_COLS + 1):
            value = ws.cell(row=5 + r, column=c + 1).value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"skipped: well {letter}{c} is not a number")
            rows.append(
                [
                    project,
                    serum,
                    parameter,
                    initials,
                    f"{letter}{c}",
                    f"{float(value):.3f}",
                ]
            )
    return (project, serum, parameter, initials), rows


def duplicate_reason(quartet, known):
    if quartet in known:
        return "skipped: plate already in mock_db (" + ", ".join(quartet) + ")"
    return None


def known_plates(path):
    plates = set()
    with open(os.path.join(path, "mock_db.csv"), newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            plates.add(
                (row["project"], row["serums"], row["PARAMETERS"], row["initals"])
            )
    return plates


def append_rows(path, rows):
    path = os.path.join(path, "mock_db.csv")
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        needs_nl = False
        if size:
            handle.seek(-1, os.SEEK_END)
            needs_nl = handle.read(1) not in b"\r\n"
    with open(path, "a", newline="", encoding="utf-8") as handle:
        if needs_nl:
            handle.write("\n")
        csv.writer(handle).writerows(rows)


def xlsx_files(root):
    found = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            if name.lower().endswith(".xlsx"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def log_skip(filename, quartet, reason):
    if not reason.startswith("skipped:"):
        reason = f"skipped: {reason}"
    stamp = datetime.now().isoformat(timespec="seconds")
    plate = ", ".join(map(str, quartet)) if quartet else ""
    os.makedirs(os.path.dirname(artifacts_logs) or ".", exist_ok=True)
    with open(artifacts_logs, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {filename}: {plate} | {reason}\n")


def _self_check():
    global artifacts_logs
    ws = build_workbook(PROJECTS[0], SERUMS[0], PARAMETERS[0], INITIALS[0]).active
    quartet, rows = plate_rows(ws)
    assert len(rows) == 96
    assert duplicate_reason(quartet, set()) is None
    assert duplicate_reason(quartet, {quartet}) == (
        "skipped: plate already in mock_db (" + ", ".join(quartet) + ")"
    )
    saved = artifacts_logs
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_w2_log_check")
    artifacts_logs = os.path.join(folder, "logs")
    try:
        log_skip("bad.xlsx", quartet, "skipped: A2 serum not allowed")
        logged = open(artifacts_logs, encoding="utf-8").read()
        assert f"{', '.join(quartet)} | skipped: A2 serum not allowed" in logged
    finally:
        artifacts_logs = saved
        if os.path.isfile(os.path.join(folder, "logs")):
            os.remove(os.path.join(folder, "logs"))
        if os.path.isdir(folder):
            os.rmdir(folder)


def main():


    #Confirm a fake build of workbook.
    _self_check()

    if not os.path.isdir(RAW):
        raise FileNotFoundError(f"dataset directory missing: {RAW}")

    #Build Set List of known plates.    
    known = known_plates(DB)

    accepted = skipped = 0

    #Cycle Through All Workbooks in the directory.
    for path in xlsx_files(RAW):
        name = os.path.basename(path)
        quartet = None
        try:
            ws = load_workbook(path).active
            quartet = tuple(ws[cell].value for cell in ("A1", "A2", "A3", "A4"))
            quartet, rows = plate_rows(ws)
        except Exception as exc:
            log_skip(name, quartet, str(exc))
            skipped += 1
            continue
        reason = duplicate_reason(quartet, known)
        if reason:
            log_skip(name, quartet, reason)
            skipped += 1
            continue
        append_rows(DB, rows)
        known.add(quartet)
        accepted += 1
    print(f"accepted {accepted}, skipped {skipped}")
    if skipped:
        sys.exit(1)


if __name__ == "__main__":
    main()
