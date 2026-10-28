"""Section 7.1 — concurrent load test, ONE engine at a time.
Workloads: Q4 depth 10, and Q7 length-only bound 6 (the selected, improved SQL).
1, 4, 8, 16 clients x 3 repetitions. Each client: own process, own persistent connection,
warms up A-B-C once, waits at a Barrier, then cycles A-B-C until 15 s after release,
finishing any cycle it started. 60 s query timeout. Correctness is checked after timing.

Run:
    docker compose stop neo4j ;   docker compose start postgres
    docker compose run --rm app python loadtest.py pg
    docker compose stop postgres; docker compose start neo4j
    docker compose run --rm app python loadtest.py neo
Outputs: results/load_raw_<engine>.csv (every request), results/load_reps_<engine>.csv,
         results/load_summary_<engine>.csv
"""
import csv
import json
import math
import multiprocessing as mp
import os
import socket
import statistics
import sys
import time
from datetime import datetime
from time import perf_counter

import psycopg
from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from db import normalize
from queries import KIGALI, SETS, Q4_SQL, q4_cypher, Q7_SQL_IMPROVED, q7_cypher, params_for

ENGINE = sys.argv[1] if len(sys.argv) > 1 else ""
if ENGINE not in ("pg", "neo"):
    sys.exit(__doc__)

# --probe: one 16-client Q7 run with a 45 s window, results NOT saved, so you have time
# to collect `docker stats` and wait-event evidence from a second terminal (Section 7.2).
PROBE = "--probe" in sys.argv
CLIENT_COUNTS = (16,) if PROBE else (1, 4, 8, 16)
REPETITIONS = 1 if PROBE else 3
WINDOW = 45 if PROBE else 15   # seconds after barrier release in which new cycles may start
TIMEOUT = 60           # per query
CYCLE = ("A", "B", "C")

WORKLOADS = {
    "Q4-d10": dict(sql=Q4_SQL, cypher=q4_cypher(10), expected="Q4-{s}-d10",
                   params=lambda s: {"account": SETS[s]["account"], "depth": 10}),
    "Q7-b6": dict(sql=Q7_SQL_IMPROVED, cypher=q7_cypher(6), expected="Q7-{s}-b6",
                  params=lambda s: dict(params_for(s), bound=6)),
}

ctx = mp.get_context("fork")
START = ctx.Value("d", 0.0)          # common start time, set once when the barrier releases


def mark_start():                    # Barrier action: runs exactly once per release
    START.value = time.monotonic()


def canon(rows):
    return json.loads(json.dumps(normalize(rows), default=str))


# ---- database access inside one process -------------------------------------------------
def open_runner():
    """Return run(query_sql, query_cypher, params) using one persistent connection."""
    if ENGINE == "pg":
        conn = psycopg.connect(autocommit=True)
        conn.execute(f"SET statement_timeout = {TIMEOUT * 1000}")

        def run(sql, cypher, params):
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

        def classify(e):
            return "timeout" if isinstance(e, psycopg.errors.QueryCanceled) else "error"
        return run, classify, conn.close

    driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                  auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
    state = {"session": driver.session(database="neo4j")}

    def run(sql, cypher, params):
        try:
            res = state["session"].run(Query(cypher, timeout=TIMEOUT), params)
            return [tuple(r.values()) for r in res]
        except Neo4jError:
            state["session"].close()
            state["session"] = driver.session(database="neo4j")
            raise

    def classify(e):
        return "timeout" if "TimedOut" in (getattr(e, "code", "") or "") else "error"
    return run, classify, driver.close


def client(cid, workload, barrier, out_q):
    w = WORKLOADS[workload]
    run, classify, close = open_runner()
    for s in CYCLE:                                     # warm-up A-B-C once, untimed
        run(w["sql"], w["cypher"], w["params"](s))
    barrier.wait()                                      # synchronized start
    start = START.value
    deadline = start + WINDOW
    log, cycle = [], 0
    while time.monotonic() < deadline:                  # start cycles until the deadline...
        cycle += 1
        for s in CYCLE:                                 # ...and finish any started cycle
            t_submit = time.monotonic()
            t0 = perf_counter()
            try:
                rows, status, err = run(w["sql"], w["cypher"], w["params"](s)), "ok", ""
            except (psycopg.Error, Neo4jError) as e:
                rows, status, err = None, classify(e), str(e).splitlines()[0][:120]
            latency_ms = (perf_counter() - t0) * 1000
            t_done = time.monotonic()
            log.append(dict(client=cid, cycle=cycle, set=s, submit_s=round(t_submit - start, 4),
                            done_s=round(t_done - start, 4), latency_ms=round(latency_ms, 3),
                            status=status, rows=None if rows is None else canon(rows), error=err))
    close()
    out_q.put(log)


# ---- monitor: count active queries during the window (evidence of concurrency) ------------
def active_count(mon):
    if ENGINE == "pg":
        return mon.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active' "
                           "AND backend_type = 'client backend' AND pid <> pg_backend_pid()"
                           ).fetchone()[0]
    with mon.session(database="neo4j") as s:
        return sum(1 for r in s.run("SHOW TRANSACTIONS YIELD currentQuery "
                                    "RETURN currentQuery")
                   if "SHOW TRANSACTIONS" not in (r["currentQuery"] or ""))


def wait_for_engine():
    other, port = ("neo4j", 7687) if ENGINE == "pg" else ("postgres", 5432)
    try:
        socket.create_connection((other, port), timeout=2).close()
        sys.exit(f"'{other}' is still running. Stop it first:  docker compose stop {other}")
    except OSError:
        pass
    if ENGINE == "pg":
        return psycopg.connect(autocommit=True)
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
    for _ in range(60):
        try:
            drv.verify_connectivity()
            return drv
        except ServiceUnavailable:
            time.sleep(2)
    sys.exit("Neo4j did not become available")


def cpu_snapshot():
    """VM-wide CPU jiffies (/proc/stat is not namespaced in containers) and this
    container's own CPU seconds (its cgroup = the load-generator processes)."""
    with open("/proc/stat") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)          # idle + iowait
    total = sum(parts[:8])                                           # exclude guest time
    app = None
    try:
        with open("/sys/fs/cgroup/cpu.stat") as f:                    # cgroup v2
            for line in f:
                if line.startswith("usage_usec"):
                    app = int(line.split()[1]) / 1e6
    except OSError:
        try:
            with open("/sys/fs/cgroup/cpuacct/cpuacct.usage") as f:   # cgroup v1
                app = int(f.read()) / 1e9
        except OSError:
            pass
    return time.monotonic(), total, idle, app


def cpu_report(a, b):
    hz = os.sysconf("SC_CLK_TCK")
    elapsed = b[0] - a[0]
    busy = ((b[1] - a[1]) - (b[2] - a[2])) / hz / elapsed
    app = (b[3] - a[3]) / elapsed if a[3] is not None and b[3] is not None else None
    n = os.cpu_count()
    line = f"VM CPU busy {busy:.2f} of {n} vCPUs ({100 * busy / n:.0f}%)"
    if app is not None:
        line += (f"  |  load generator (app container) {app:.2f} vCPUs"
                 f"  |  database + everything else {busy - app:.2f} vCPUs")
    return line


def pg_waits(mon):
    return mon.execute(
        "SELECT coalesce(wait_event_type, 'CPU (running)'), coalesce(wait_event, '-') "
        "FROM pg_stat_activity WHERE backend_type = 'client backend' AND state = 'active' "
        "AND pid <> pg_backend_pid()").fetchall()


def p95(values):
    s = sorted(values)
    return s[math.ceil(0.95 * len(s)) - 1] if s else None


def one_repetition(workload, n, rep, mon):
    barrier = ctx.Barrier(n + 1, action=mark_start)     # n clients + this monitor
    out_q = ctx.Queue()
    procs = [ctx.Process(target=client, args=(i, workload, barrier, out_q)) for i in range(n)]
    for p in procs:
        p.start()
    barrier.wait()
    start = START.value
    started_cat = datetime.now(KIGALI).isoformat(timespec="seconds")
    cpu0 = cpu_snapshot() if PROBE else None
    waits = {}
    peak, samples = 0, []
    logs = []
    while len(logs) < n:                                # sample while clients run
        if time.monotonic() - start < WINDOW + TIMEOUT + 5:
            try:
                c = active_count(mon)
                samples.append(c)
                peak = max(peak, c)
                if PROBE and ENGINE == "pg" and time.monotonic() - start < WINDOW:
                    for w in pg_waits(mon):
                        waits[w] = waits.get(w, 0) + 1
            except Exception:
                pass
        try:
            logs.append(out_q.get(timeout=1))
        except Exception:
            pass
    for p in procs:
        p.join()

    if PROBE:
        print("\n=== Resource evidence during the probe ===")
        print(cpu_report(cpu0, cpu_snapshot()))
        if waits:
            total = sum(waits.values())
            print(f"PostgreSQL active-backend samples ({total}, about 1 per second x active backends):")
            for (kind, event), cnt in sorted(waits.items(), key=lambda x: -x[1]):
                print(f"   {kind:15} {event:22} {cnt:>6}  ({100 * cnt / total:.0f}%)")
        print()

    reqs = [r for log in logs for r in log]
    expected = {s: json.load(open(f"results/compare/{WORKLOADS[workload]['expected'].format(s=s)}.json"))["pg"]
                for s in CYCLE}
    for r in reqs:                                      # correctness, after timing
        r["correct"] = r["status"] == "ok" and r["rows"] == expected[r["set"]]
    ok = [r for r in reqs if r["status"] == "ok"]
    correct = [r for r in ok if r["correct"]]
    elapsed = max(r["done_s"] for r in reqs)            # release -> final cycle finished
    lat = [r["latency_ms"] for r in ok]
    rep_row = dict(engine=ENGINE, workload=workload, clients=n, rep=rep, start_cat=started_cat,
                   requests=len(reqs), ok=len(ok), correct=len(correct),
                   errors=sum(r["status"] == "error" for r in reqs),
                   timeouts=sum(r["status"] == "timeout" for r in reqs),
                   elapsed_s=round(elapsed, 3), throughput_rps=round(len(correct) / elapsed, 3),
                   median_ms=round(statistics.median(lat), 2) if lat else None,
                   p95_ms=round(p95(lat), 2) if lat else None,
                   peak_active=peak, mean_active=round(statistics.mean(samples), 1) if samples else None)
    for r in reqs:
        r.update(engine=ENGINE, workload=workload, clients=n, rep=rep)
        r["rows"] = len(r["rows"]) if r["rows"] is not None else ""
    return rep_row, reqs


def main():
    mon = wait_for_engine()
    if PROBE:
        for name in list(WORKLOADS):
            if name != "Q7-b6":
                del WORKLOADS[name]
        print("PROBE MODE: Q7-b6, 16 clients, 45 s, nothing saved. Collect evidence now.\n")
    raw, reps, summary = [], [], []
    print(f"Engine {ENGINE}: workloads {list(WORKLOADS)}, clients {CLIENT_COUNTS}, "
          f"{REPETITIONS} repetitions, {WINDOW}s window\n")
    for workload in WORKLOADS:
        for n in CLIENT_COUNTS:
            rows = []
            for rep in range(1, REPETITIONS + 1):
                rep_row, reqs = one_repetition(workload, n, rep, mon)
                rows.append(rep_row)
                reps.append(rep_row)
                raw.extend(reqs)
                print(f"{workload:7} {n:>2} clients rep {rep}: {rep_row['correct']:>5} correct / "
                      f"{rep_row['requests']:>5} req in {rep_row['elapsed_s']:6.2f}s  "
                      f"throughput {rep_row['throughput_rps']:8.2f}/s  median {rep_row['median_ms']:>9} ms  "
                      f"p95 {rep_row['p95_ms']:>9} ms  err {rep_row['errors']} to {rep_row['timeouts']}  "
                      f"active peak {rep_row['peak_active']} mean {rep_row['mean_active']}", flush=True)
            med = lambda k: statistics.median(r[k] for r in rows if r[k] is not None)
            summary.append(dict(engine=ENGINE, workload=workload, clients=n,
                                throughput_rps=round(med("throughput_rps"), 3),
                                median_ms=round(med("median_ms"), 2), p95_ms=round(med("p95_ms"), 2),
                                errors=sum(r["errors"] for r in rows),
                                timeouts=sum(r["timeouts"] for r in rows),
                                all_correct=all(r["correct"] == r["ok"] for r in rows)))
    if PROBE:
        return
    for path, data in ((f"results/load_raw_{ENGINE}.csv", raw), (f"results/load_reps_{ENGINE}.csv", reps),
                       (f"results/load_summary_{ENGINE}.csv", summary)):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)

    print("\n=== Combination summaries (median of 3 repetitions) ===")
    print(f"{'workload':8} {'clients':>7} {'throughput/s':>13} {'median ms':>10} {'p95 ms':>10} "
          f"{'errors':>6} {'timeouts':>8} {'correct':>8}")
    for s in summary:
        print(f"{s['workload']:8} {s['clients']:>7} {s['throughput_rps']:>13.2f} {s['median_ms']:>10.2f} "
              f"{s['p95_ms']:>10.2f} {s['errors']:>6} {s['timeouts']:>8} {str(s['all_correct']):>8}")


if __name__ == "__main__":
    main()
