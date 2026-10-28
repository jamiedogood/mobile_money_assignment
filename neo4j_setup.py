"""Section 3.2 step 3 — constraints and index after import, timed.
Run (Neo4j started): docker compose run --rm app python neo4j_setup.py
"""
import os
import time
from time import perf_counter

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

STATEMENTS = [
    "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS "
    "FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
    "CREATE CONSTRAINT account_id_unique IF NOT EXISTS "
    "FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique IF NOT EXISTS "
    "FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE RANGE INDEX transfer_occurred_at IF NOT EXISTS "
    "FOR ()-[t:TRANSFER]-() ON (t.occurred_at)",
]

driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                              auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
for attempt in range(60):                 # Neo4j may still be starting
    try:
        driver.verify_connectivity()
        break
    except ServiceUnavailable:
        time.sleep(2)

with driver.session(database="neo4j") as s:
    start = perf_counter()
    for stmt in STATEMENTS:
        t = perf_counter()
        s.run(stmt).consume()
        print(f"{perf_counter() - t:8.2f} s  {stmt}")
    t = perf_counter()
    s.run("CALL db.awaitIndexes(1800)").consume()   # wait until every index is ONLINE
    print(f"{perf_counter() - t:8.2f} s  CALL db.awaitIndexes(1800)")
    print(f"\nTotal setup seconds: {perf_counter() - start:.2f}")

    print("\n=== Constraints ===")
    for r in s.run("SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
                   "RETURN name, type, entityType, labelsOrTypes, properties ORDER BY name"):
        print(f"  {r['name']:22} {r['type']:12} {r['entityType']:12} "
              f"{r['labelsOrTypes']} {r['properties']}")

    print("\n=== Indexes ===")
    for r in s.run("SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, "
                   "state, populationPercent "
                   "RETURN name, type, entityType, labelsOrTypes, properties, state, "
                   "populationPercent ORDER BY name"):
        print(f"  {r['name']:22} {r['type']:7} {r['entityType']:12} {str(r['labelsOrTypes']):14} "
              f"{str(r['properties']):18} {r['state']:7} {r['populationPercent']}%")
driver.close()
