"""Section 1.1 — print versions, hardware and database memory settings.
Run: docker compose run --rm app python check_env.py
Screenshot the output (with taskbar + clock visible).
NOTE: CPU/RAM here are what the Docker VM sees. Also record your host OS/CPU/RAM
from the host itself (e.g. Windows: `systeminfo`, macOS: About This Mac).
"""
import os
import platform
import sys

import neo4j
import numpy
import psycopg

print("=== Client side ===")
print("Python      :", sys.version.split()[0])
print("psycopg     :", psycopg.__version__)
print("neo4j driver:", neo4j.__version__)
print("numpy       :", numpy.__version__)
print("OS (container):", platform.platform())
print("CPU count   :", os.cpu_count())
with open("/proc/meminfo") as f:
    total_kb = int(f.readline().split()[1])
print(f"RAM visible : {total_kb * 1024 / 1e9:.2f} GB")

print("\n=== PostgreSQL ===")
with psycopg.connect() as conn:  # uses PGHOST/PGUSER/PGPASSWORD/PGDATABASE
    for setting in ["server_version", "TimeZone", "shared_buffers",
                    "effective_cache_size", "work_mem", "maintenance_work_mem",
                    "max_wal_size", "max_parallel_workers_per_gather"]:
        value = conn.execute(f"SHOW {setting}").fetchone()[0]
        print(f"{setting:32} {value}")
    print("now() in session:", conn.execute("SELECT now()").fetchone()[0])

print("\n=== Neo4j ===")
driver = neo4j.GraphDatabase.driver(os.environ["NEO4J_URI"],
                                    auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
with driver.session(database="neo4j") as s:
    for r in s.run("CALL dbms.components() YIELD name, versions, edition "
                   "RETURN name, versions, edition"):
        print(r["name"], r["versions"], r["edition"])
    for r in s.run("SHOW SETTINGS YIELD name, value "
                   "WHERE name STARTS WITH 'server.memory' "
                   "   OR name = 'db.transaction.timeout' "
                   "RETURN name, value ORDER BY name"):
        print(f"{r['name']:40} {r['value']}")
driver.close()
print("\nBoth connections OK.")
