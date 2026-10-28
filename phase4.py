"""Section 4 — run Q1, Q2, Q3 in both databases, compare, save full outputs, plot Q2.
Run (both databases started):
    docker compose run --rm app python phase4.py          # all three
    docker compose run --rm app python phase4.py q1 q3    # a subset
Outputs: results/q1.csv, results/q2.csv, results/q2_daily.png, results/q3_<set>.csv
"""
import csv
import json
import os
import sys
from datetime import datetime
from time import perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from db import close, normalize, run_neo, run_pg
from queries import KIGALI, QUERIES, SETS, params_for

os.makedirs("results", exist_ok=True)
wanted = {a.lower() for a in sys.argv[1:]} or {"q1", "q2", "q3"}


def cat(ts):
    return datetime.fromtimestamp(ts, KIGALI).strftime("%Y-%m-%d %H:%M:%S")


def both(name, params):
    sql, cypher = QUERIES[name]
    t = perf_counter(); pg_rows = run_pg(sql, params); t_pg = perf_counter() - t
    t = perf_counter(); neo_rows = run_neo(cypher, params); t_neo = perf_counter() - t
    return pg_rows, neo_rows, normalize(pg_rows) == normalize(neo_rows), t_pg, t_neo


def save(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(normalize(rows))


# ---------------------------------------------------------------------------- Q1
if "q1" in wanted:
    print("\n==================== Q1 Account activity (09:45-10:45 CAT) ====================")
    print(f"{'set':3} {'account':>8} {'start (epoch)':>14} {'end (epoch)':>12}  {'window CAT':32}"
          f" {'PG count':>8} {'PG RWF':>10} {'Neo count':>9} {'Neo RWF':>10}  match")
    out = []
    for s in SETS:
        p = params_for(s)
        pg_rows, neo_rows, same, _, _ = both("Q1", p)
        (pc, ps), (nc, ns) = pg_rows[0], neo_rows[0]
        print(f"{s:3} {p['account']:>8} {p['start']:>14} {p['end']:>12}  "
              f"{cat(p['start'])} -> {cat(p['end'])[11:]:8}"
              f" {pc:>8} {ps:>10,} {nc:>9} {ns:>10,}  {'YES' if same else 'NO'}")
        out.append((s, p["account"], p["start"], p["end"], pc, ps, nc, ns, same))
    save("results/q1.csv", ["set", "account", "start", "end", "pg_count", "pg_total_rwf",
                            "neo_count", "neo_total_rwf", "match"], out)

# ---------------------------------------------------------------------------- Q2
if "q2" in wanted:
    print("\n==================== Q2 Daily activity (CAT days) ====================")
    pg_rows, neo_rows, same, t_pg, t_neo = both("Q2", {})
    print(f"PostgreSQL {t_pg:.1f} s, Neo4j {t_neo:.1f} s (informal; Section 6 does proper timing)")
    print(f"{'day':12} {'transfers':>10} {'total RWF':>16}")
    for day, n, total in pg_rows:
        print(f"{day!s:12} {n:>10,} {total:>16,}")

    with open("data/capture_audit.json") as f:
        audit = json.load(f)["streams"][-1]
    days, count_sum, value_sum = len(pg_rows), sum(r[1] for r in pg_rows), sum(r[2] for r in pg_rows)
    print(f"\nDays returned        : {days}   (expect 30)  {'ok' if days == 30 else 'MISMATCH'}")
    print(f"Sum of daily counts  : {count_sum:,}   capture {audit['transfer_count']:,}  "
          f"{'ok' if count_sum == audit['transfer_count'] else 'MISMATCH'}")
    print(f"Sum of daily RWF     : {value_sum:,}   capture {audit['sum_amount_rwf']:,}  "
          f"{'ok' if value_sum == audit['sum_amount_rwf'] else 'MISMATCH'}")
    print(f"PostgreSQL vs Neo4j  : {len(pg_rows)} vs {len(neo_rows)} rows, identical: "
          f"{'YES' if same else 'NO'}")
    save("results/q2.csv", ["day", "transfers", "total_rwf"], pg_rows)

    labels = [r[0].day for r in pg_rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax1.bar(labels, [r[1] for r in pg_rows], color="#3b6ea5")
    ax1.set_ylabel("Transfers per day (count)")
    ax1.set_ylim(min(r[1] for r in pg_rows) * 0.999, max(r[1] for r in pg_rows) * 1.0005)
    ax1.set_title("Q2 Daily transfer activity, September 2026 (CAT days)")
    ax2.plot(labels, [r[2] / 1e9 for r in pg_rows], marker="o", color="#c0504d")
    ax2.set_ylabel("Value per day (billion RWF)")
    ax2.set_xlabel("Day of September 2026")
    ax2.set_xticks(labels)
    for ax in (ax1, ax2):
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig("results/q2_daily.png", dpi=150)
    print("Chart saved: results/q2_daily.png")

# ---------------------------------------------------------------------------- Q3
if "q3" in wanted:
    print("\n==================== Q3 Shared devices (overlapping intervals) ====================")
    for s in SETS:
        p = params_for(s)
        pg_rows, neo_rows, same, _, _ = both("Q3", p)
        types = {}
        for r in pg_rows:
            types[r[2]] = types.get(r[2], 0) + 1
        print(f"\nSet {s}  account {p['account']}:  PG {len(pg_rows)} rows, Neo4j {len(neo_rows)} rows,"
              f"  identical: {'YES' if same else 'NO'}   by type: {types}")
        print(f"   {'other':>8} {'device':>8} {'access_type':16} {'overlap':>9}")
        for other, dev, typ, a, b in pg_rows[:12]:
            print(f"   {other:>8} {dev:>8} {typ:16} [{a:>2},{b:>2}]")
        if len(pg_rows) > 12:
            print(f"   ... {len(pg_rows) - 12} more in results/q3_{s}.csv")
        save(f"results/q3_{s}.csv",
             ["other_account", "device_id", "access_type", "overlap_start", "overlap_end"], pg_rows)

close()
