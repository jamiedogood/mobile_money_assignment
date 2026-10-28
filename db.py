"""Shared database helpers (Section 6.1 asks for run_pg / run_neo).
Connections are created once and reused (persistent), as the timing sections require.
"""
import os
from decimal import Decimal

import psycopg
from neo4j import GraphDatabase

_pg = None
_neo = None


def pg():
    global _pg
    if _pg is None or _pg.closed:
        _pg = psycopg.connect(autocommit=True)   # PGHOST/PGUSER/PGPASSWORD/PGDATABASE from env
    return _pg


def neo():
    global _neo
    if _neo is None:
        import time
        from neo4j.exceptions import ServiceUnavailable
        _neo = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                    auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
        for _ in range(60):                   # wait up to 120 s for Neo4j to finish starting
            try:
                _neo.verify_connectivity()
                break
            except ServiceUnavailable:
                time.sleep(2)
    return _neo


def run_pg(query, params=None):
    """Run SQL with %(name)s parameters; return every row as a tuple."""
    with pg().cursor() as cur:
        cur.execute(query, params or {})
        return cur.fetchall() if cur.description else []


def run_neo(query, params=None):
    """Run Cypher with $name parameters; return every row as a tuple."""
    with neo().session(database="neo4j") as s:
        return [tuple(r.values()) for r in s.run(query, params or {})]


def _norm(v):
    """Make PostgreSQL and Neo4j values comparable."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if hasattr(v, "iso_format"):            # neo4j.time.Date / DateTime
        return v.iso_format()
    if hasattr(v, "isoformat"):             # datetime.date / datetime
        return v.isoformat()
    if isinstance(v, (list, tuple)):        # arrays / lists, e.g. transfer-ID sequences
        return tuple(_norm(x) for x in v)
    return v


def normalize(rows):
    """Normalize every value, then sort rows, so results compare exactly."""
    return sorted(tuple(_norm(v) for v in row) for row in rows)


def close():
    global _pg, _neo
    if _pg is not None:
        _pg.close()
        _pg = None
    if _neo is not None:
        _neo.close()
        _neo = None
