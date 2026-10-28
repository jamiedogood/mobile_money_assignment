"""Section 3.3 — trace one account to its owner, its devices and an outgoing transfer,
with SQL JOINs and Cypher MATCH, and check both return the same records.
Run (both databases started): docker compose run --rm app python trace_account.py [account_id]
"""
import sys
from datetime import datetime, timezone, timedelta

from db import run_neo, run_pg, close

ACCOUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 8
CAT = timezone(timedelta(hours=2))

# ---- 1. Account -> owner -> devices -> first outgoing transfer ------------------------
SQL_TRACE = """
SELECT a.account_id, a.role, c.customer_id, c.region,
       d.device_id, d.access_type, ad.first_day, ad.last_day, ad.observations,
       t.transfer_id, t.receiver_id, r.role AS receiver_role, t.occurred_at, t.amount_rwf
FROM accounts a
JOIN customers c        ON c.customer_id = a.customer_id          -- FK: ownership
JOIN account_devices ad ON ad.account_id = a.account_id           -- FK: device use
JOIN devices d          ON d.device_id   = ad.device_id
JOIN LATERAL (                                                     -- FK: transfer sender
    SELECT * FROM transfers t
    WHERE t.sender_id = a.account_id
    ORDER BY t.occurred_at, t.transfer_id
    LIMIT 1
) t ON true
JOIN accounts r         ON r.account_id = t.receiver_id           -- FK: transfer receiver
WHERE a.account_id = %(account)s
ORDER BY d.device_id
"""

CYPHER_TRACE = """
MATCH (c:Customer)-[:OWNS]->(a:Account {account_id: $account})-[u:USED_DEVICE]->(d:Device)
CALL (a) {
    MATCH (a)-[t:TRANSFER]->(r:Account)
    RETURN t, r
    ORDER BY t.occurred_at, t.transfer_id
    LIMIT 1
}
RETURN a.account_id, a.role, c.customer_id, c.region,
       d.device_id, d.access_type, u.first_day, u.last_day, u.observations,
       t.transfer_id, r.account_id, r.role, t.occurred_at, t.amount_rwf
ORDER BY d.device_id
"""

# ---- 2. Repeated payments from this account (why one edge per transfer matters) -------
SQL_REPEATS = """
SELECT receiver_id, count(*) AS payments, sum(amount_rwf) AS total_rwf,
       min(occurred_at) AS first_at, max(occurred_at) AS last_at
FROM transfers
WHERE sender_id = %(account)s
GROUP BY receiver_id
HAVING count(*) > 1
ORDER BY payments DESC, receiver_id
LIMIT 5
"""

CYPHER_REPEATS = """
MATCH (:Account {account_id: $account})-[t:TRANSFER]->(r:Account)
WITH r.account_id AS receiver_id, count(t) AS payments, sum(t.amount_rwf) AS total_rwf,
     min(t.occurred_at) AS first_at, max(t.occurred_at) AS last_at
WHERE payments > 1
RETURN receiver_id, payments, total_rwf, first_at, last_at
ORDER BY payments DESC, receiver_id
LIMIT 5
"""


def cat(ts):
    return datetime.fromtimestamp(ts, CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def norm(rows):
    return sorted(tuple(int(v) if isinstance(v, int) else v for v in row) for row in rows)


def compare(title, sql, cypher, headers, ts_cols=()):
    params = {"account": ACCOUNT}
    pg_rows, neo_rows = run_pg(sql, params), run_neo(cypher, params)
    print(f"\n=== {title} ===")
    print(" | ".join(headers))
    for row in pg_rows:
        print(" | ".join(cat(v) if i in ts_cols else str(v) for i, v in enumerate(row)))
    same = norm(pg_rows) == norm(neo_rows)
    print(f"PostgreSQL rows: {len(pg_rows)}   Neo4j rows: {len(neo_rows)}   "
          f"identical: {'YES' if same else 'NO'}")
    if not same:
        print("Neo4j returned:")
        for row in neo_rows:
            print("  ", row)
    return same


ok = compare(f"Account {ACCOUNT}: owner, devices, first outgoing transfer",
             SQL_TRACE, CYPHER_TRACE,
             ["account", "role", "customer", "region", "device", "access_type",
              "first_day", "last_day", "obs", "transfer_id", "receiver", "receiver_role",
              "occurred_at", "amount_rwf"], ts_cols=(12,))
ok &= compare(f"Account {ACCOUNT}: receivers paid more than once",
              SQL_REPEATS, CYPHER_REPEATS,
              ["receiver", "payments", "total_rwf", "first_at", "last_at"], ts_cols=(3, 4))
print("\nBOTH MODELS MATCH" if ok else "\nMISMATCH")
close()
