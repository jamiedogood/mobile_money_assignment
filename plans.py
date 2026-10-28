"""Section 6.2 — query plans OUTSIDE timing: EXPLAIN (ANALYZE, BUFFERS) / PROFILE
for Q2, Q4 set B depth 10 and Q7 set B bound 6.
Run with the matching engine started:
    docker compose run --rm app python plans.py pg
    docker compose run --rm app python plans.py neo
    docker compose run --rm app python plans.py pg --improved    (Section 6.3, Q7 only)
Outputs: results/plans/<case>_<engine>.txt
"""
import os
import sys

from cases import build_cases
from db import close, neo, run_pg

ENGINE = sys.argv[1] if len(sys.argv) > 1 else ""
IMPROVED = "--improved" in sys.argv
if ENGINE not in ("pg", "neo"):
    sys.exit(__doc__)

if IMPROVED:
    from queries import Q7_SQL_IMPROVED
    cases = {c["id"]: c for c in build_cases(q7_sql=Q7_SQL_IMPROVED)}
    wanted = ["Q7-B-b6"]
else:
    cases = {c["id"]: c for c in build_cases()}
    wanted = ["Q2-month", "Q4-B-d10", "Q7-B-b6"]
os.makedirs("results/plans", exist_ok=True)


def neo_profile(case):
    lines = []

    def walk(op, depth):
        args = op.get("args", {})
        lines.append(f"{'  ' * depth}+{op.get('operatorType')}  rows={op.get('rows')} "
                     f"dbHits={op.get('dbHits')} pageCacheHits={op.get('pageCacheHits')} "
                     f"pageCacheMisses={op.get('pageCacheMisses')}"
                     + (f"  | {args['Details']}" if args.get("Details") else ""))
        for child in op.get("children", []):
            walk(child, depth + 1)

    with neo().session(database="neo4j") as s:
        result = s.run("PROFILE " + case["cypher"], case["params"])
        rows = list(result)
        summary = result.consume()
    prof = summary.profile
    root_args = prof.get("args", {})
    lines.append(f"rows returned: {len(rows)}   planner: {root_args.get('planner')}   "
                 f"runtime: {root_args.get('runtime')}   global memory: {root_args.get('GlobalMemory')}   "
                 f"server time to result: {summary.result_available_after + summary.result_consumed_after} ms")
    walk(prof, 0)
    total_hits = 0

    def sum_hits(op):
        nonlocal total_hits
        total_hits += op.get("dbHits") or 0
        for ch in op.get("children", []):
            sum_hits(ch)
    sum_hits(prof)
    lines.append(f"TOTAL dbHits: {total_hits:,}")
    return "\n".join(lines)


def pg_explain(case):
    rows = run_pg("EXPLAIN (ANALYZE, BUFFERS) " + case["sql"], case["params"])
    return "\n".join(r[0] for r in rows)


for cid in wanted:
    case = cases[cid]
    text = pg_explain(case) if ENGINE == "pg" else neo_profile(case)
    name = f"{cid}_{ENGINE}{'_improved' if IMPROVED else ''}"
    with open(f"results/plans/{name}.txt", "w") as f:
        f.write(text + "\n")
    print(f"\n==================== {name} ====================\n{text}", flush=True)
close()
