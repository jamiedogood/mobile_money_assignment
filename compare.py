"""Section 6.1 — run all 61 cases in both databases and compare exactly.
Q7 lengths are compared separately from the validity of a supporting path.
Run (both databases started):
    docker compose run --rm app python compare.py               # original SQL
    docker compose run --rm app python compare.py --improved    # Section 6.3 Q7 SQL (later)
Outputs: results/compare_status.csv and results/compare/<case>.json (full rows, both engines).
"""
import csv
import json
import os
import sys
from collections import defaultdict
from time import perf_counter

from cases import build_cases
from db import close, normalize, run_neo, run_pg
from queries import Q7_VERIFY_SQL

improved = "--improved" in sys.argv
if improved:
    from queries import Q7_SQL_IMPROVED as Q7_VARIANT
    cases = build_cases(q7_sql=Q7_VARIANT)
else:
    cases = build_cases()

out_dir = "results/compare_improved" if improved else "results/compare"
os.makedirs(out_dir, exist_ok=True)


def run(fn, query, params):
    t = perf_counter()
    try:
        return fn(query, params), None, perf_counter() - t
    except Exception as e:                       # record, never hide, errors
        return None, f"{type(e).__name__}: {e}"[:200], perf_counter() - t


def verify_q7_path(case, hops):
    """Retrieve one shortest path from Neo4j and check it independently in PostgreSQL."""
    p = case["params"]
    accounts, tids = run_neo(case["path_cypher"], p)[0]
    detail = run_pg(Q7_VERIFY_SQL, {"ids": list(tids)})
    checks = [len(tids) == hops, len(detail) == len(tids),
              accounts[0] == p["account"], accounts[-1] == p["destination"]]
    for i, (tid, snd, rcv, s_role, r_role, ts) in enumerate(detail):
        checks += [snd == accounts[i], rcv == accounts[i + 1],
                   s_role == "person", r_role == "person"]
    return all(checks), accounts, list(tids)


print(f"Running {len(cases)} cases ({'improved' if improved else 'original'} Q7 SQL)\n")
print(f"{'case':12} {'PG rows':>8} {'Neo rows':>9} {'PG s':>7} {'Neo s':>7}  {'status':10} {'Q7 path':8}")
status_rows = []
for c in cases:
    pg_rows, pg_err, t_pg = run(run_pg, c["sql"], c["params"])
    neo_rows, neo_err, t_neo = run(run_neo, c["cypher"], c["params"])
    path_status, path = "", None

    if pg_err or neo_err:
        status = "ERROR"
    elif c["q"] == "Q7":
        pg_len = pg_rows[0][0] if pg_rows else None
        neo_len = neo_rows[0][0] if neo_rows else None
        status = "MATCH" if pg_len == neo_len else "MISMATCH"
        if neo_len is not None:
            ok, accounts, tids = verify_q7_path(c, neo_len)
            path_status = "valid" if ok else "INVALID"
            path = dict(accounts=accounts, transfer_ids=tids)
        else:
            path_status = "no route"
    else:
        status = "MATCH" if normalize(pg_rows) == normalize(neo_rows) else "MISMATCH"

    print(f"{c['id']:12} {len(pg_rows or []):>8} {len(neo_rows or []):>9} {t_pg:>7.2f} {t_neo:>7.2f}"
          f"  {status:10} {path_status:8}", flush=True)
    if pg_err:
        print(f"   PG error: {pg_err}")
    if neo_err:
        print(f"   Neo4j error: {neo_err}")

    with open(os.path.join(out_dir, f"{c['id']}.json"), "w") as f:
        json.dump(dict(case=c["id"], params=c["params"], status=status, path_status=path_status,
                       pg=normalize(pg_rows) if pg_rows is not None else pg_err,
                       neo=normalize(neo_rows) if neo_rows is not None else neo_err,
                       q7_path=path), f, indent=1, default=str)
    status_rows.append((c["id"], c["q"], c["set"], len(pg_rows or []), len(neo_rows or []),
                        status, path_status, round(t_pg, 3), round(t_neo, 3)))

with open(os.path.join("results", "compare_status_improved.csv" if improved
                       else "compare_status.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "question", "set", "pg_rows", "neo_rows", "status", "q7_path",
                "pg_seconds", "neo_seconds"])
    w.writerows(status_rows)

# Summary per question
summary = defaultdict(lambda: [0, 0])
for r in status_rows:
    summary[r[1]][1] += 1
    summary[r[1]][0] += r[5] == "MATCH"
print("\n=== Summary ===")
for q in sorted(summary):
    m, n = summary[q]
    print(f"  {q}: {m}/{n} match")
total_match = sum(m for m, _ in summary.values())
paths = [r[6] for r in status_rows if r[1] == "Q7" and r[6] not in ("", "no route")]
print(f"  TOTAL: {total_match}/{len(status_rows)} match")
print(f"  Q7 supporting paths: {paths.count('valid')}/{len(paths)} valid")
print("\nALL 61 CASES MATCH" if total_match == len(status_rows) == 61 else "\nCHECK MISMATCHES ABOVE")
close()
