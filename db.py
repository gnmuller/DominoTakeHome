import os
import sqlite3
from datetime import datetime

DIR = "/mnt/data/Worker2DatabaseProxy"
PATH = os.path.join(DIR, "plates.sqlite")
VIEW_COLUMNS = (
    "project",
    "serums",
    "PARAMETERS",
    "initals",
    "cell",
    "value",
    "lab",
    "instrument",
    "run_date",
    "flag",
    "day",
    "analyst",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plates (
  id           integer PRIMARY KEY,
  project      text NOT NULL CHECK (project GLOB 'Domino-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
  serum        text NOT NULL,
  parameter    text NOT NULL,
  initials     text NOT NULL CHECK (initials GLOB '[A-Z][A-Z]'),
  lab          text NOT NULL CHECK (lab IN ('Lab1', 'Lab2', 'Lab3')),
  day          integer NOT NULL CHECK (day >= 1),
  run_date     text NOT NULL CHECK (run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  analyst      text NOT NULL CHECK (analyst GLOB '[A-J]'),
  instrument   text NOT NULL CHECK (length(instrument) > 0),
  source_file  text NOT NULL,
  ingested_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE (project, serum, parameter, initials, lab, day, run_date)
);

CREATE TABLE IF NOT EXISTS wells (
  plate_id  integer NOT NULL REFERENCES plates (id),
  well      text NOT NULL CHECK (
    well GLOB '[A-H][1-9]' OR well GLOB '[A-H]1[0-2]'
  ),
  value     real,
  flag      text NOT NULL DEFAULT '' CHECK (flag IN ('', 'blank', 'overflow', 'na')),
  PRIMARY KEY (plate_id, well),
  CHECK (
    (flag = '' AND value IS NOT NULL)
    OR (flag <> '' AND value IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS plates_browse ON plates (project, lab, run_date, serum);

CREATE TABLE IF NOT EXISTS ingest_log (
  id           integer PRIMARY KEY,
  logged_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  source_file  text NOT NULL,
  outcome      text NOT NULL CHECK (outcome IN ('accepted', 'skipped')),
  detail       text NOT NULL,
  project      text,
  serum        text,
  parameter    text,
  initials     text,
  lab          text,
  day          integer,
  run_date     text
);

CREATE VIEW IF NOT EXISTS mock_db AS
SELECT
  p.project AS project,
  p.serum AS serums,
  p.parameter AS PARAMETERS,
  p.initials AS initals,
  w.well AS cell,
  CASE WHEN w.value IS NULL THEN '' ELSE printf('%.3f', w.value) END AS value,
  p.lab AS lab,
  p.instrument AS instrument,
  printf('%s%s%s',
    strftime('%d', p.run_date),
    CASE strftime('%m', p.run_date)
      WHEN '01' THEN 'Jan'
      WHEN '02' THEN 'Feb'
      WHEN '03' THEN 'Mar'
      WHEN '04' THEN 'Apr'
      WHEN '05' THEN 'May'
      WHEN '06' THEN 'Jun'
      WHEN '07' THEN 'Jul'
      WHEN '08' THEN 'Aug'
      WHEN '09' THEN 'Sep'
      WHEN '10' THEN 'Oct'
      WHEN '11' THEN 'Nov'
      WHEN '12' THEN 'Dec'
    END,
    strftime('%Y', p.run_date)
  ) AS run_date,
  w.flag AS flag,
  'day ' || p.day AS day,
  p.analyst AS analyst
FROM wells AS w
JOIN plates AS p ON p.id = w.plate_id;
"""


def day_number(value):
    return int(str(value).split()[-1])


def iso_date(value):
    return datetime.strptime(str(value), "%d%b%Y").date().isoformat()


def connect(path=PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure(path=PATH):
    conn = connect(path)
    conn.executescript(_SCHEMA)
    return conn


def load_rows(path=PATH):
    conn = connect(path)
    try:
        cur = conn.execute(
            """
            SELECT * FROM mock_db
            ORDER BY project, serums, PARAMETERS, initals, lab, day, run_date,
                     substr(cell, 1, 1), CAST(substr(cell, 2) AS integer)
            """
        )
        columns = [item[0] for item in cur.description]
        return [dict(row) for row in cur], columns
    finally:
        conn.close()


def insert_plate(conn, quartet, rows, source_file):
    if len(rows) != 96:
        raise ValueError(f"skipped: plate has {len(rows)} wells")
    project, serum, parameter, initials, lab, day, run_date = quartet
    cur = conn.execute(
        """
        INSERT INTO plates (
            project, serum, parameter, initials, lab, day, run_date,
            analyst, instrument, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project,
            serum,
            parameter,
            initials,
            lab,
            day_number(day),
            iso_date(run_date),
            rows[0][11],
            rows[0][7],
            source_file,
        ),
    )
    plate_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO wells (plate_id, well, value, flag) VALUES (?, ?, ?, ?)",
        [
            (plate_id, row[4], None if row[5] == "" else float(row[5]), row[9])
            for row in rows
        ],
    )


def log_outcome(conn, source_file, outcome, detail, quartet=None):
    project = serum = parameter = initials = lab = day = run_date = None
    if quartet:
        values = list(quartet[:7])
        values.extend([None] * (7 - len(values)))
        project, serum, parameter, initials, lab, day, run_date = values
        project = None if project is None else str(project)
        serum = None if serum is None else str(serum)
        parameter = None if parameter is None else str(parameter)
        initials = None if initials is None else str(initials)
        lab = None if lab is None else str(lab)
        day = None if day is None else day_number(day)
        run_date = None if run_date is None else iso_date(run_date)
    conn.execute(
        """
        INSERT INTO ingest_log (
            source_file, outcome, detail, project, serum, parameter,
            initials, lab, day, run_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_file,
            outcome,
            detail,
            project,
            serum,
            parameter,
            initials,
            lab,
            day,
            run_date,
        ),
    )
