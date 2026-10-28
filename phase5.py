"""Section 5 — Q4 to Q7 in both databases, one question per run.
Run (both databases started):
    docker compose run --rm app python phase5.py q4 4 6      # predict, then:
    docker compose run --rm app python phase5.py q4 8 10
    docker compose run --rm app python phase5.py q5
    docker compose run --rm app python phase5.py q6
    docker compose run --rm app python phase5.py q7
Full outputs go to results/.
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
from queries import (KIGALI, SETS, params_for, Q4_SQL, q4_cypher, Q4_PATH_CYPHER,
                     Q5_SQL, Q5_CYPHER, Q6_SQL, Q6_CYPHER, Q7_SQL, q7_cypher,
                     q7_path_cypher, Q7_VERIFY_SQL, TRANSFER_DETAIL_SQL)

os.makedirs("results", exist_ok=True)
args = [a.lower() for a in sys.argv[1:]]
cmd = args[0] if args else ""


def cat(ts):
    return datetime.fromtimestamp(ts, KIGALI).strftime("%Y-%m-%d %H:%M:%S CAT")


def timed(fn, query, params):
    t = perf_counter()
    rows = fn(query, params)
    return rows, perf_counter() - t


def save(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(normalize(rows))


def show_transfers(ids, title):
    """Print given transfers in order with CAT time, gap and amount ratio."""
    print(f"\n--- {title} ---")
    print(f"{'transfer_id':>12} {'sender':>8} -> {'receiver':>8}  {'time':24} {'gap':>6} "
          f"{'amount RWF':>11} {'vs previous':>12}")
    prev_ts = prev_amt = None
    for tid, snd, rcv, ts, amt in run_pg(TRANSFER_DETAIL_SQL, {"ids": list(ids)}):
        gap = f"{ts - prev_ts}s" if prev_ts else ""
        ratio = f"{100 * amt / prev_amt:.3f}%" if prev_amt else ""
        print(f"{tid:>12} {snd:>8} -> {rcv:>8}  {cat(ts):24} {gap:>6} {amt:>11,} {ratio:>12}")
        prev_ts, prev_amt = ts, amt


# =========================================================================== Q4
if cmd == "q4":
    depths = [int(a) for a in args[1:]] or [4, 6, 8, 10]
    store_path = "results/q4.json"
    store = json.load(open(store_path)) if os.path.exists(store_path) else {}

    for d in depths:
        print(f"\n==================== Q4 depth {d} ====================")
        for s, cfg in SETS.items():
            acct = cfg["account"]
            pg_rows, t_pg = timed(run_pg, Q4_SQL, {"account": acct, "depth": d})
            neo_rows, t_neo = timed(run_neo, q4_cypher(d), {"account": acct})
            same = normalize(pg_rows) == normalize(neo_rows)
            regions = {r: c for r, c in pg_rows}
            total = sum(regions.values())
            print(f"Set {s} acct {acct:>6}  total {total:>7,}  "
                  + "  ".join(f"{r} {c:,}" for r, c in pg_rows)
                  + f"   identical: {'YES' if same else 'NO'}   (PG {t_pg:.1f}s, Neo4j {t_neo:.1f}s)",
                  flush=True)
            if not same:
                print("   Neo4j:", neo_rows)
            store.setdefault(s, {})[str(d)] = dict(
                pg=regions, neo={r: c for r, c in neo_rows}, total=total, match=same,
                pg_seconds=round(t_pg, 2), neo_seconds=round(t_neo, 2))
        with open(store_path, "w") as f:
            json.dump(store, f, indent=2)

    if 4 in depths:
        rows = run_neo(Q4_PATH_CYPHER, {"account": SETS["A"]["account"]})
        if rows:
            nodes, links = rows[0]
            path = nodes[0] + "".join(f" {l} {n}" for l, n in zip(links, nodes[1:]))
            print(f"\nSupporting 4-link path from set A:\n  {path}")

    # Count-versus-depth plot from everything measured so far.
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for s in SETS:
        if s in store:
            ds = sorted(int(k) for k in store[s])
            ax.plot(ds, [store[s][str(k)]["total"] for k in ds], marker="o", label=f"Set {s}")
    ax.set_xlabel("Maximum links (OWNS / USED_DEVICE, either direction)")
    ax.set_ylabel("Distinct other accounts reached (count)")
    ax.set_title("Q4 Accounts reached versus search depth")
    ax.set_xticks([4, 6, 8, 10])
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig("results/q4_depth.png", dpi=150)
    print("\nChart saved: results/q4_depth.png   Data: results/q4.json")

# =========================================================================== Q5 / Q6
elif cmd in ("q5", "q6"):
    q = cmd.upper()
    sql, cypher = (Q5_SQL, Q5_CYPHER) if q == "Q5" else (Q6_SQL, Q6_CYPHER)
    noun = "chains" if q == "Q5" else "cycles"
    example = None
    print(f"\n==================== {q} {'Rapid onward payments' if q == 'Q5' else 'Circular payments'} ====================")
    for s in SETS:
        p = params_for(s)
        pg_rows, t_pg = timed(run_pg, sql, p)
        neo_rows, t_neo = timed(run_neo, cypher, p)
        same = normalize(pg_rows) == normalize(neo_rows)
        print(f"Set {s} acct {p['account']:>6}: PG {len(pg_rows)} {noun}, Neo4j {len(neo_rows)} {noun}, "
              f"identical: {'YES' if same else 'NO'}   (PG {t_pg:.2f}s, Neo4j {t_neo:.2f}s)")
        for row in pg_rows:
            if q == "Q5":
                print(f"      transfers {row[0]}, {row[1]}, {row[2]} -> final receiver {row[3]}")
            else:
                print(f"      length {row[1]}: {list(row[0])}")
        if not same:
            print("   Neo4j:", neo_rows)
        if pg_rows and example is None:
            example = (s, pg_rows[0])
        header = (["first_id", "second_id", "third_id", "final_receiver"] if q == "Q5"
                  else ["transfer_ids", "length"])
        save(f"results/{cmd}_{s}.csv", header, pg_rows)
    if example:
        s, row = example
        ids = row[:3] if q == "Q5" else row[0]
        show_transfers(ids, f"Example {noun[:-1]} from set {s}")

# =========================================================================== Q7
elif cmd == "q7":
    print("\n==================== Q7 Shortest person-only transfer connection ====================")
    out = []
    for bound in (4, 6):
        for s in SETS:
            p = dict(params_for(s), bound=bound)
            pg_rows, t_pg = timed(run_pg, Q7_SQL, p)
            neo_rows, t_neo = timed(run_neo, q7_cypher(bound), p)
            pg_len = pg_rows[0][0] if pg_rows else None
            neo_len = neo_rows[0][0] if neo_rows else None
            same = pg_len == neo_len
            shown = lambda v: "no route" if v is None else str(v)
            print(f"bound {bound}  set {s}  {p['account']:>6} -> {p['destination']:>6}:  "
                  f"PG {shown(pg_len):>8}   Neo4j {shown(neo_len):>8}   identical: {'YES' if same else 'NO'}"
                  f"   (PG {t_pg:.1f}s, Neo4j {t_neo:.2f}s)", flush=True)

            path_ok = None
            if neo_len is not None:
                accounts, tids = run_neo(q7_path_cypher(bound), p)[0]
                detail = run_pg(Q7_VERIFY_SQL, {"ids": list(tids)})
                checks = [len(tids) == neo_len, len(detail) == len(tids),
                          accounts[0] == p["account"], accounts[-1] == p["destination"]]
                for i, (tid, snd, rcv, s_role, r_role, ts) in enumerate(detail):
                    checks += [snd == accounts[i], rcv == accounts[i + 1],
                               s_role == "person", r_role == "person"]
                path_ok = all(checks)
                print(f"      path: {' -> '.join(map(str, accounts))}")
                for tid, snd, rcv, s_role, r_role, ts in detail:
                    print(f"        transfer {tid:>9}: {snd:>6} ({s_role}) -> {rcv:>6} ({r_role})  {cat(ts)}")
                print(f"      checks (IDs exist, direction, roles, endpoints, length): "
                      f"{'ALL OK' if path_ok else 'FAILED'}")
            out.append((s, bound, p["account"], p["destination"], pg_len, neo_len, same, path_ok))
    save("results/q7.csv", ["set", "bound", "account", "destination", "pg_hops", "neo_hops",
                            "match", "path_checks_ok"],
         [tuple("" if v is None else v for v in r) for r in out])

else:
    print(__doc__)

close()
