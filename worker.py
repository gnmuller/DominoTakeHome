import os
import random
import uuid
from datetime import date

from openpyxl import Workbook, load_workbook

_pool = random.Random(1)


def _unique(draw, n):
    seen = set()
    while len(seen) < n:
        seen.add(draw())
    return sorted(seen)


#A1
PROJECTS = _unique(lambda: f"Domino-{_pool.randint(0, 9_999_999):07d}", 7)
#A2
SERUMS = [
    "Pooled Normal Human Serum",
    "Individual Donor Serum",
    "Heat-Inactivated Human Serum",
    "Fetal Bovine Serum",
]
#A3
PARAMETERS = [
    "Absorbance (OD450)",
    "Absorbance (OD405)",
    "Absorbance (OD492)",
    "Fluorescence (RFU)",
    "Luminescence (RLU)",
    "Concentration (ng/mL)",
    "Percent Inhibition",
]
#A4
INITIALS = _unique(
    lambda: "".join(_pool.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(2)),
    10,
)

assert len(PROJECTS) == 7
assert len(SERUMS) == 4
assert len(PARAMETERS) == 7
assert len(INITIALS) == 10

#Standard 96 well plate
ROWS = "ABCDEFGH"
N_COLS = 12


def results_dir():

    #Write under the dataset mount. Database comes later.

    dataset = "/domino/datasets/local/Worker1Raw"
    if not os.path.isdir(dataset):
        raise FileNotFoundError(f"dataset directory missing: {dataset}")
    path = os.path.join(dataset, "results")
    os.makedirs(path, exist_ok=True)
    return path


def fake_readings():

    #N_Cols AND ROWS
    #Are standard and defined up top


    random.seed(4)

    #Uniform Range Choosen because
    #Usual readable window for an ELISA plate reader at 450 nm
    return [
        [round(random.uniform(0.050, 2.500), 3) for _ in range(N_COLS)]
        for _ in ROWS
    ]


def build_workbook(project, serum, parameter, initials):
    wb = Workbook()
    ws = wb.active
    ws.title = "Plate"
    ws["A1"] = project
    ws["A2"] = serum
    ws["A3"] = parameter
    ws["A4"] = initials



    for col in range(1, N_COLS + 1):
        ws.cell(row=5, column=col + 1, value=col)


    readings = fake_readings()

    
    for r, letter in enumerate(ROWS):
        ws.cell(row=5 + r, column=1, value=letter)
        for c, value in enumerate(readings[r]):
            ws.cell(row=5 + r, column=2 + c, value=value)
    return wb


def assert_layout(path, project, serum, parameter, initials):
    ws = load_workbook(path).active
    assert ws["A1"].value == project
    assert ws["A2"].value == serum
    assert ws["A3"].value == parameter
    assert ws["A4"].value == initials
    cells = [
        cell.value
        for row in ws.iter_rows(min_row=5, max_row=12, min_col=2, max_col=13)
        for cell in row
    ]
    assert len(cells) == 96
    assert all(isinstance(value, (int, float)) for value in cells)


def main():
    project = random.choice(PROJECTS)
    serum = random.choice(SERUMS)
    parameter = random.choice(PARAMETERS)
    initials = random.choice(INITIALS)
    today = date.today()
    suffix = uuid.uuid4().hex[:8]
    name = (
        f"assay_plate_{today.year}-{today.month:02d}-{today.day:02d}"
        f"_{initials}_{suffix}.xlsx"
    )
    path = os.path.join(results_dir(), name)
    build_workbook(project, serum, parameter, initials).save(path)

    #Checkworkbook
    assert_layout(path, project, serum, parameter, initials)
    print(path)


if __name__ == "__main__":
    main()
