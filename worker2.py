import csv
import os
import re
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

# ponytail: a comma is always a decimal mark; "1.234,5" is rejected.
HOLES = {"OVRFLW", "OVERFLOW", "****", "#N/A", "#DIV/0!", "ND", "N.A.", "N.A", "NA", "BLANK"}
SERUM_ALIASES = {
    "pooled normal human serum": "Pooled Normal Human Serum",
    "pooled nhs": "Pooled Normal Human Serum",
    "pooled normal human serun": "Pooled Normal Human Serum",
    "individual donor serum": "Individual Donor Serum",
    "donor serum": "Individual Donor Serum",
    "heat-inactivated human serum": "Heat-Inactivated Human Serum",
    "heat inactivated human serum": "Heat-Inactivated Human Serum",
    "hi human serum": "Heat-Inactivated Human Serum",
    "fetal bovine serum": "Fetal Bovine Serum",
    "fbs": "Fetal Bovine Serum",
}
PARAMETER_ALIASES = {
    "absorbance (od450)": "Absorbance (OD450)",
    "od450": "Absorbance (OD450)",
    "od 450": "Absorbance (OD450)",
    "absorbance (od405)": "Absorbance (OD405)",
    "od405": "Absorbance (OD405)",
    "od 405": "Absorbance (OD405)",
    "absorbance (od492)": "Absorbance (OD492)",
    "od492": "Absorbance (OD492)",
    "od 492": "Absorbance (OD492)",
    "fluorescence (rfu)": "Fluorescence (RFU)",
    "rfu": "Fluorescence (RFU)",
    "luminescence (rlu)": "Luminescence (RLU)",
    "rlu": "Luminescence (RLU)",
    "concentration (ng/ml)": "Concentration (ng/mL)",
    "ng/ml": "Concentration (ng/mL)",
    "percent inhibition": "Percent Inhibition",
    "% inhibition": "Percent Inhibition",
    "%inhib": "Percent Inhibition",
}
LABS = {
    "lab1": "Lab1",
    "west lab": "Lab2",
    "lab2": "Lab2",
    "east lab": "Lab3",
    "lab3": "Lab3",
}

RAW = "/mnt/data/Worker1Raw"
DB = "/mnt/data/Worker2DatabaseProxy"
artifacts_logs = "/mnt/artifacts/logs"


def _token(value):
    return "" if value is None else " ".join(str(value).strip().lower().split())


def canon_project(value):
    text = "" if value is None else str(value).strip()
    match = re.fullmatch(r"(?i)domino[-\s]?(\d{7})", text)
    if not match:
        return text
    return f"Domino-{int(match.group(1)):07d}"


def canon_name(value, aliases, allowed):
    text = "" if value is None else str(value).strip()
    if text in allowed:
        return text
    return aliases.get(_token(value), text)


def canon_lab(value):
    if value is None or str(value).strip() == "":
        return "Lab1"
    return LABS.get(_token(value), str(value).strip())


def parse_well(value, well):
    if isinstance(value, bool):
        raise ValueError(f"skipped: well {well} is not a number")
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"skipped: well {well} is not a number")
    text = value.strip()
    if text == "" or text.upper() in HOLES:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    lower = text.lower()
    for unit in ("ng/ml", "rfu", "rlu", "od"):
        if lower.endswith(unit):
            text = text[: -len(unit)].strip()
            break
    if "," in text and "." in text:
        raise ValueError(f"skipped: well {well} is not a number")
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError(f"skipped: well {well} is not a number") from None


def plate_rows(ws):
    project = canon_project(ws["A1"].value)
    serum = canon_name(ws["A2"].value, SERUM_ALIASES, SERUMS)
    parameter = canon_name(ws["A3"].value, PARAMETER_ALIASES, PARAMETERS)
    initials = "" if ws["A4"].value is None else str(ws["A4"].value).strip().upper()
    lab = canon_lab(ws["C1"].value)
    fields = (
        ("A1", "project", PROJECTS, project),
        ("A2", "serum", SERUMS, serum),
        ("A3", "parameter", PARAMETERS, parameter),
        ("A4", "initials", INITIALS, initials),
    )
    for cell, label, allowed, value in fields:
        if value not in allowed:
            raise ValueError(f'skipped: {cell} {label} not allowed: "{value}"')
    rows = []
    dropped = 0
    for r, letter in enumerate(ROWS):
        got = ws.cell(row=5 + r, column=1).value
        got = "" if got is None else str(got).strip().upper()
        if got != letter:
            raise ValueError(f"skipped: row {letter} label is {got!r}")
        for c in range(1, N_COLS + 1):
            well = f"{letter}{c}"
            number = parse_well(ws.cell(row=5 + r, column=c + 1).value, well)
            if number is None:
                dropped += 1
                continue
            rows.append(
                [
                    project,
                    serum,
                    parameter,
                    initials,
                    well,
                    f"{number:.3f}",
                    lab,
                ]
            )
    return (project, serum, parameter, initials, lab), rows, dropped


def duplicate_reason(quartet, known):
    if quartet in known:
        return "skipped: plate already in mock_db (" + ", ".join(quartet) + ")"
    return None


def ensure_lab_column(path):
    file_path = os.path.join(path, "mock_db.csv")
    with open(file_path, encoding="utf-8", newline="") as handle:
        content = handle.read()
    if not content:
        return
    line, sep, rest = content.partition("\n")
    header_line = line[:-1] if line.endswith("\r") else line
    if "lab" in next(csv.reader([header_line])):
        return
    nl = "\r\n" if line.endswith("\r") else ("\n" if sep else "")
    with open(file_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(header_line + ",lab" + nl + rest)


def known_plates(path):
    plates = set()
    with open(os.path.join(path, "mock_db.csv"), newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            plates.add(
                (
                    row["project"],
                    row["serums"],
                    row["PARAMETERS"],
                    row["initals"],
                    row.get("lab") or "Lab1",
                )
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


def log_line(filename, quartet, message):
    stamp = datetime.now().isoformat(timespec="seconds")
    plate = ", ".join(map(str, quartet)) if quartet else ""
    os.makedirs(os.path.dirname(artifacts_logs) or ".", exist_ok=True)
    with open(artifacts_logs, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {filename}: {plate} | {message}\n")


def log_skip(filename, quartet, reason):
    if not reason.startswith("skipped:"):
        reason = f"skipped: {reason}"
    log_line(filename, quartet, reason)


def _self_check():
    global artifacts_logs
    from worker1_lab2 import dirty as dirty_west
    from worker1_lab3 import dirty as dirty_east

    ws = build_workbook(PROJECTS[0], SERUMS[0], PARAMETERS[0], INITIALS[0]).active
    quartet, rows, dropped = plate_rows(ws)
    assert dropped == 0 and len(rows) == 96 and quartet[-1] == "Lab1"
    assert duplicate_reason(quartet, set()) is None
    assert duplicate_reason(quartet, {quartet}) == (
        "skipped: plate already in mock_db (" + ", ".join(quartet) + ")"
    )

    west = build_workbook(PROJECTS[0], SERUMS[3], PARAMETERS[0], INITIALS[0]).active
    original_a3 = west.cell(row=5, column=4).value
    dirty_west(west, PROJECTS[0], SERUMS[3], PARAMETERS[0], INITIALS[0])
    string_well = west.cell(row=5, column=4).value
    assert isinstance(string_well, str)
    quartet, rows, dropped = plate_rows(west)
    by_well = {row[4]: row[5] for row in rows}
    assert quartet == (PROJECTS[0], SERUMS[3], PARAMETERS[0], INITIALS[0], "Lab2")
    assert dropped == 2 and len(rows) == 94
    assert "A1" not in by_well and "A2" not in by_well
    assert by_well["A3"] == f"{float(string_well):.3f}" == f"{original_a3:.3f}"

    percent = PARAMETERS[-1]
    east = build_workbook(PROJECTS[1], SERUMS[2], percent, INITIALS[1]).active
    original_a1 = east.cell(row=5, column=2).value
    original_a3 = east.cell(row=5, column=4).value
    dirty_east(east, PROJECTS[1], SERUMS[2], percent, INITIALS[1])
    assert east.cell(row=5, column=1).value == "a"
    assert east["A14"].value
    quartet, rows, dropped = plate_rows(east)
    by_well = {row[4]: row[5] for row in rows}
    assert quartet == (PROJECTS[1], SERUMS[2], percent, INITIALS[1], "Lab3")
    assert dropped == 1 and "A4" not in by_well
    assert by_well["A1"] == f"{original_a1:.3f}"
    assert by_well["A3"] == f"{original_a3:.3f}"
    assert by_well["A5"] == "-0.015" and by_well["A6"] == "-0.008"
    assert by_well["A7"] == "45.000"

    saved = artifacts_logs
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_w2_log_check")
    db_dir = os.path.join(folder, "db")
    artifacts_logs = os.path.join(folder, "logs")
    os.makedirs(db_dir, exist_ok=True)
    try:
        log_skip("bad.xlsx", quartet, "skipped: A2 serum not allowed")
        log_line("good.xlsx", quartet, "accepted")
        logged = open(artifacts_logs, encoding="utf-8").read()
        assert f"{', '.join(quartet)} | skipped: A2 serum not allowed" in logged
        assert "good.xlsx:" in logged and f"{', '.join(quartet)} | accepted" in logged
        db_path = os.path.join(db_dir, "mock_db.csv")
        with open(db_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("project,serums,PARAMETERS,initals,cell,value\n")
            handle.write(
                f"{PROJECTS[0]},{SERUMS[0]},{PARAMETERS[0]},{INITIALS[0]},A1,1.000\n"
            )
        ensure_lab_column(db_dir)
        assert known_plates(db_dir) == {
            (PROJECTS[0], SERUMS[0], PARAMETERS[0], INITIALS[0], "Lab1")
        }
        with open(db_path, "a", encoding="utf-8", newline="") as handle:
            handle.write(
                f"{PROJECTS[1]},{SERUMS[1]},{PARAMETERS[1]},{INITIALS[1]},B1,2.000,Lab2\n"
            )
        assert (
            PROJECTS[1],
            SERUMS[1],
            PARAMETERS[1],
            INITIALS[1],
            "Lab2",
        ) in known_plates(db_dir)
    finally:
        artifacts_logs = saved
        for name in ("logs", os.path.join("db", "mock_db.csv")):
            file_path = os.path.join(folder, name)
            if os.path.isfile(file_path):
                os.remove(file_path)
        if os.path.isdir(db_dir):
            os.rmdir(db_dir)
        if os.path.isdir(folder):
            os.rmdir(folder)


def main():


    #Confirm a fake build of workbook.
    _self_check()

    if not os.path.isdir(RAW):
        raise FileNotFoundError(f"dataset directory missing: {RAW}")

    #Build Set List of known plates.
    ensure_lab_column(DB)
    known = known_plates(DB)

    accepted = skipped = 0

    #Cycle Through All Workbooks in the directory.
    for path in xlsx_files(RAW):
        name = os.path.basename(path)
        quartet = None
        try:
            ws = load_workbook(path).active
            quartet = tuple(ws[cell].value for cell in ("A1", "A2", "A3", "A4"))
            quartet, rows, dropped = plate_rows(ws)
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
        detail = "accepted" if not dropped else f"accepted, dropped {dropped} wells"
        log_line(name, quartet, detail)
        accepted += 1
    print(f"accepted {accepted}, skipped {skipped}")
    if skipped:
        sys.exit(1)


if __name__ == "__main__":
    main()
