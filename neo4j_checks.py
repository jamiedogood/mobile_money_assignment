"""Section 3.2 step 4 — verify the graph against capture.py, plus store sizes.
Run (Neo4j started): docker compose run --rm app python neo4j_checks.py
"""
import json
import os
from time import perf_counter

from neo4j import GraphDatabase

with open("data/capture_audit.json") as f:
    audit = json.load(f)
transfer_audit = audit["streams"][-1]

NODES = {"Customer": 228_000, "Account": 248_000, "Device": 228_600}
RELS = {"OWNS": 248_000, "USED_DEVICE": 285_600, "TRANSFER": 20_003_300}
all_ok = True


def report(name, got, expected):
    global all_ok
    ok = got == expected
    all_ok &= ok
    print(f"  {name:34} {got!s:>16} {expected!s:>16}  {'ok' if ok else 'MISMATCH'}")


driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                              auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
with driver.session(database="neo4j") as s:
    one = lambda q: s.run(q).single()

    print(f"  {'check':34} {'graph':>16} {'expected':>16}")
    print("=== Nodes ===")
    for label, n in NODES.items():
        report(f":{label}", one(f"MATCH (n:{label}) RETURN count(n) AS c")["c"], n)
    report("all nodes", one("MATCH (n) RETURN count(n) AS c")["c"], 704_600)

    print("=== Relationships ===")
    for rel, n in RELS.items():
        report(f":{rel}", one(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")["c"], n)
    report("all relationships", one("MATCH ()-[r]->() RETURN count(r) AS c")["c"], 20_536_900)

    print("=== Account roles ===")
    roles = {r["role"]: r["c"] for r in
             s.run("MATCH (a:Account) RETURN a.role AS role, count(*) AS c ORDER BY role")}
    for role, n in {"agent": 2_000, "merchant": 6_000, "person": 240_000}.items():
        report(f"role = {role}", roles.get(role, 0), n)

    print("=== One owner per account ===")
    owners = {r["owners"]: r["accounts"] for r in s.run(
        "MATCH (a:Account) "
        "WITH COUNT { (:Customer)-[:OWNS]->(a) } AS owners "
        "RETURN owners, count(*) AS accounts ORDER BY owners")}
    print(f"  owner-count distribution: {owners}")
    report("accounts with exactly 1 owner", owners.get(1, 0), 248_000)

    print("=== Transfer audit totals ===")
    t = one("MATCH ()-[t:TRANSFER]->() RETURN count(t) AS n, min(t.occurred_at) AS lo, "
            "max(t.occurred_at) AS hi, sum(t.amount_rwf) AS total")
    report("transfer count", t["n"], transfer_audit["transfer_count"])
    report("earliest occurred_at", t["lo"], transfer_audit["earliest_occurred_at"])
    report("latest occurred_at", t["hi"], transfer_audit["latest_occurred_at"])
    report("sum amount_rwf", t["total"], transfer_audit["sum_amount_rwf"])

    print("=== Unique transfer_id (10 buckets by transfer_id % 10, ~2-4 min) ===")
    # Each bucket is its own short transaction and returns two numbers, so nothing large
    # is held in memory or sent to Python. If every bucket has count == distinct count and
    # the buckets sum to the total, no transfer_id appears twice.
    start = perf_counter()
    total = total_distinct = 0
    for k in range(10):
        r = s.run("MATCH ()-[t:TRANSFER]->() WHERE t.transfer_id % 10 = $k "
                  "RETURN count(t) AS n, count(DISTINCT t.transfer_id) AS d", k=k).single()
        print(f"  bucket {k}: {r['n']:>9,} transfers, {r['d']:>9,} distinct ids", flush=True)
        total += r["n"]
        total_distinct += r["d"]
    report("transfers across buckets", total, RELS["TRANSFER"])
    report("distinct transfer_id", total_distinct, RELS["TRANSFER"])
    print(f"  (checked in {perf_counter() - start:.1f} s)")
driver.close()


def dir_bytes(path):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(path) for f in files)


print("=== Store sizes (1 GB = 1,000,000,000 bytes) ===")
store = dir_bytes("/neo4jdata/databases/neo4j")
txlog = dir_bytes("/neo4jdata/transactions/neo4j")
print(f"  store           {store / 1e9:.3f} GB")
print(f"  transaction log {txlog / 1e9:.3f} GB")
print(f"  total           {(store + txlog) / 1e9:.3f} GB")

print("\nALL CHECKS PASSED" if all_ok else "\nSOME CHECKS FAILED")
