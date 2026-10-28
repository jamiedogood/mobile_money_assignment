"""Section 6.2 — time 21 fixed cases in ONE engine (the other must be stopped).
3 untimed warm-ups (180 s limit) + 5 measured runs (60 s limit) per case.
Timing covers submission through receipt of the final row (perf_counter).
Timeouts/errors are recorded separately, never as completed timings.
Answers are checked against the Section 6.1 results, outside the timer.

Run:
    docker compose stop neo4j ;   docker compose start postgres
    docker compose run --rm app python benchmark.py pg
    docker compose stop postgres; docker compose start neo4j
    docker compose run --rm app python benchmark.py neo
    (Section 6.3:  python benchmark.py pg --improved   times only the 4 Q7 cases, improved SQL)
Outputs: results/bench_raw_<engine>[_improved].csv, results/bench_summary_<engine>[_improved].csv
"""
import csv
import json
import os
import socket
import statistics
import sys
from datetime import datetime
from time import perf_counter

import psycopg
from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError

from cases import build_cases
from db import normalize
from queries import KIGALI

ENGINE = sys.argv[1] if len(sys.argv) > 1 else ""
IMPROVED = "--improved" in sys.argv
if ENGINE not in ("pg", "neo") or (IMPROVED and ENGINE != "pg"):
    sys.exit(__doc__)

WARMUPS, RUNS = 3, 5
WARMUP_TIMEOUT, RUN_TIMEOUT = 180, 60

# The 21 timed cases: B and E for Q1/Q3/Q5/Q6, full month for Q2,
# B/E at all four depths for Q4, B/E at both bounds for Q7.
TIMED = (["Q1-B", "Q1-E", "Q2-month", "Q3-B", "Q3-E"]
         + [f"Q4-{s}-d{d}" for s in "BE" for d in (4, 6, 8, 10)]
         + ["Q5-B", "Q5-E", "Q6-B", "Q6-E"]
         + [f"Q7-{s}-b{b}" for s in "BE" for b in (4, 6)])
assert len(TIMED) == 21

if IMPROVED:
    from queries import Q7_SQL_IMPROVED
    all_cases = {c["id"]: c for c in build_cases(q7_sql=Q7_SQL_IMPROVED)}
    TIMED = [c for c in TIMED if c.startswith("Q7")]          # the 4 revised SQL cases
else:
    all_cases = {c["id"]: c for c in build_cases()}
cases = [all_cases[i] for i in TIMED]


# ---- one database service at a time ---------------------------------------------------
def reachable(host, port):
    try:
        socket.create_connection((host, port), timeout=2).close()
        return True
    except OSError:
        return False


other, other_port = ("neo4j", 7687) if ENGINE == "pg" else ("postgres", 5432)
if reachable(other, other_port):
    sys.exit(f"'{other}' is still running. Stop it first:  docker compose stop {other}")


# ---- persistent connection and one timed execution -----------------------------------
if ENGINE == "pg":
    conn = psycopg.connect(autocommit=True)

    def prepare(timeout):
        conn.execute(f"SET statement_timeout = {timeout * 1000}")

    def execute(case, timeout):
        with conn.cursor() as cur:
            cur.execute(case["sql"], case["params"])
            return cur.fetchall()

    def classify(e):
        return "timeout" if isinstance(e, psycopg.errors.QueryCanceled) else "error"
else:
    import time
    from neo4j.exceptions import ServiceUnavailable
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                  auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
    for attempt in range(60):                 # Neo4j needs ~10-30 s after the container starts
        try:
            driver.verify_connectivity()
            break
        except ServiceUnavailable:
            if attempt == 0:
                print("Waiting for Neo4j to accept connections ...", flush=True)
            time.sleep(2)
    else:
        sys.exit("Neo4j did not become available within 120 s")
    session = driver.session(database="neo4j")

    def prepare(timeout):
        pass

    def execute(case, timeout):
        result = session.run(Query(case["cypher"], timeout=timeout), case["params"])
        return [tuple(r.values()) for r in result]            # consume every row

    def classify(e):
        return "timeout" if "TimedOut" in (getattr(e, "code", "") or "") else "error"


def canon(rows):
    return json.loads(json.dumps(normalize(rows), default=str))


def one_run(case, timeout):
    global session
    prepare(timeout)                                           # outside the timer
    start_cat = datetime.now(KIGALI).isoformat(timespec="seconds")
    t = perf_counter()
    try:
        rows = execute(case, timeout)
        duration = perf_counter() - t
        status, err = "ok", ""
    except (psycopg.Error, Neo4jError) as e:
        duration = perf_counter() - t
        rows, status, err = None, classify(e), str(e).splitlines()[0][:150]
        if ENGINE == "neo":                                    # fresh session after a failure
            session.close()
            session = driver.session(database="neo4j")
    return start_cat, duration, rows, status, err


# ---- main loop -------------------------------------------------------------------------
suffix = f"{ENGINE}_improved" if IMPROVED else ENGINE
raw_path = f"results/bench_raw_{suffix}.csv"
summary_path = f"results/bench_summary_{suffix}.csv"
raw = []
summary = []

print(f"Engine: {ENGINE}{' (improved Q7 SQL)' if IMPROVED else ''}   cases: {len(cases)}   "
      f"{WARMUPS} warm-ups ({WARMUP_TIMEOUT}s) + {RUNS} measured ({RUN_TIMEOUT}s)\n")
for case in cases:
    expected = json.load(open(f"results/compare/{case['id']}.json"))["pg"]
    measured, statuses, all_correct = [], [], True
    for phase, n, timeout in (("warmup", WARMUPS, WARMUP_TIMEOUT), ("measured", RUNS, RUN_TIMEOUT)):
        for i in range(1, n + 1):
            start_cat, dur, rows, status, err = one_run(case, timeout)
            correct = "" if rows is None else canon(rows) == expected     # outside the timer
            raw.append(dict(case=case["id"], question=case["q"], set=case["set"],
                            params=json.dumps(case["params"]), engine=ENGINE, phase=phase, run=i,
                            start_cat=start_cat, duration_ms=round(dur * 1000, 3),
                            rows="" if rows is None else len(rows), status=status,
                            correct=correct, error=err))
            if phase == "measured":
                statuses.append(status)
                if status == "ok":
                    measured.append(dur * 1000)
                    all_correct &= bool(correct)
    timeouts, errors = statuses.count("timeout"), statuses.count("error")
    row = dict(case=case["id"], engine=ENGINE, ok_runs=len(measured), timeouts=timeouts, errors=errors,
               median_ms=round(statistics.median(measured), 2) if measured else "",
               min_ms=round(min(measured), 2) if measured else "",
               max_ms=round(max(measured), 2) if measured else "",
               all_correct=all_correct if measured else "")
    summary.append(row)
    shown = (f"median {row['median_ms']:>10,.2f} ms  min {row['min_ms']:>10,.2f}  max {row['max_ms']:>10,.2f}"
             if measured else f"{'no completed runs':>58}")
    print(f"{case['id']:10} {shown}   ok {len(measured)}/{RUNS}  timeouts {timeouts}  errors {errors}"
          f"  correct {row['all_correct']}", flush=True)

    with open(raw_path, "w", newline="") as f:                 # saved after every case
        w = csv.DictWriter(f, fieldnames=list(raw[0]))
        w.writeheader()
        w.writerows(raw)
    with open(summary_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

print(f"\nSaved {raw_path} and {summary_path}")
