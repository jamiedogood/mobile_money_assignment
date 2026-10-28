# Mobile Money Investigations with PostgreSQL and Neo4j

Advanced Big Data Analytics, Project 2.

| Member | Student ID |
| --- | --- |
| Thierry SEBAKUNZI | 101394 |
| Yves Nishyirimbere | 101388 |
| James Kwezi | 101502 |

Everything runs in Docker: PostgreSQL 17, Neo4j 5 Community, and a Python 3.12 tools container. Nothing is installed on the host except Docker Desktop.

## Requirements

- Docker Desktop (Windows with WSL2, macOS or Linux)
- About 10 GB of free disk space
- The machine used for our results: 8 vCPUs and 8.14 GB RAM visible to Docker (see `logs/` and the report, Section 1.1)

## Environment we measured with

| Component | Version / setting |
| --- | --- |
| PostgreSQL | 17.11, `timezone=Africa/Kigali`, `shared_buffers=2GB`, `effective_cache_size=6GB`, `work_mem=64MB`, `maintenance_work_mem=1GB`, `max_wal_size=8GB` |
| Neo4j | 5.26.32 Community, heap 2 GB, page cache 3 GB, `db.transaction.timeout=180s` |
| Python | 3.12.16; exact packages in `requirements.lock.txt` |

These settings are fixed in `docker-compose.yml` and were not changed during any timing.

## Generator integrity

`mobile_money_generator.py` is the supplied file, unchanged. Its SHA-256 at capture time was:

```
2ea0e59d2b7b987d84a3d151bd9d1ad7b3052bfbc25abf1466c8e94467e9455a
```

Check it at any time:

```
docker compose run --rm app python -c "import hashlib; print(hashlib.sha256(open('mobile_money_generator.py','rb').read()).hexdigest())"
```

## Run everything, in order

Commands are for PowerShell. On macOS or Linux, replace the backtick line continuation with `\`.

### 0. Configure

```
copy .env.example .env      # then set real passwords in .env (Neo4j: at least 8 characters, no $)
docker compose build app
docker compose up -d postgres neo4j
docker compose run --rm app python check_env.py               # Section 1.1
```

### 1. Capture (Section 1.2)

```
docker compose run --rm app python capture.py                 # writes data/*.csv and data/capture_audit.json
```

### 2. PostgreSQL (Section 2)

```
docker exec -i mm_postgres psql -U mm -d mobile_money -f /sql/01_tables.sql
docker exec -i mm_postgres psql -U mm -d mobile_money -f /sql/02_load.sql
docker exec -i mm_postgres psql -U mm -d mobile_money -f /sql/03_constraints_indexes.sql
docker exec -i mm_postgres psql -U mm -d mobile_money -f /sql/04_checks.sql
```

### 3. Neo4j (Section 3)

```
docker compose run --rm app python prepare_import.py          # typed copies in import/
docker compose stop neo4j postgres
docker compose run --rm --no-deps neo4j neo4j-admin database import full neo4j `
  --id-type=integer --overwrite-destination=true `
  --nodes=Customer=/import/customers.csv `
  --nodes=Account=/import/accounts.csv `
  --nodes=Device=/import/devices.csv `
  --relationships=OWNS=/import/owns.csv `
  --relationships=USED_DEVICE=/import/used_device.csv `
  --relationships=TRANSFER=/import/transfers.csv `
  --report-file=/import/import.report
docker compose up -d neo4j
docker compose run --rm app python neo4j_setup.py             # constraints + index
docker compose run --rm app python neo4j_checks.py            # counts, roles, owners, audit, sizes
Remove-Item import\*.csv                                       # temporary copies removed after checks
docker compose start postgres
docker compose run --rm app python trace_account.py           # Section 3.3
```

### 4. Questions (Sections 4 and 5), both databases running

```
docker compose run --rm app python phase4.py q1 q3
docker compose run --rm app python phase4.py q2
docker compose run --rm app python phase5.py q4 4 6
docker compose run --rm app python phase5.py q4 8 10
docker compose run --rm app python phase5.py q5
docker compose run --rm app python phase5.py q6
docker compose run --rm app python phase5.py q7
```

### 5. Correctness (Section 6.1), both databases running

```
docker compose run --rm app python compare.py                 # 61 cases, original SQL
docker compose run --rm app python csv_checks.py              # independent check against the CSVs
```

### 6. Timing (Sections 6.2 and 6.3), ONE database at a time

```
docker compose stop neo4j;    docker compose start postgres
docker compose run --rm app python benchmark.py pg
docker compose run --rm app python plans.py pg
docker compose run --rm app python plans.py pg --improved
docker compose run --rm app python benchmark.py pg --improved

docker compose stop postgres; docker compose start neo4j
docker compose run --rm app python benchmark.py neo
docker compose run --rm app python plans.py neo

docker compose start postgres                                  # both engines for the recheck
docker compose run --rm app python compare.py --improved      # 61 cases with the improved Q7 SQL
docker compose run --rm app python bench_report.py
```

### 7. Concurrency (Section 7), ONE database at a time

```
docker compose stop neo4j;    docker compose start postgres
docker compose run --rm app python loadtest.py pg
docker compose run --rm app python loadtest.py pg --probe      # resource evidence, not saved

docker compose stop postgres; docker compose start neo4j
docker compose run --rm app python loadtest.py neo
docker compose run --rm app python loadtest.py neo --probe

docker compose run --rm app python load_report.py
```

### 8. Final verification and shutdown (Section 9.2)

```
docker compose start postgres neo4j
docker compose run --rm app python compare.py --improved
docker compose stop
docker compose ps -a                                           # both services shown as exited
```

The database volumes (`pgdata`, `neo4jdata`) are kept. Never run `docker compose down -v`, which deletes them.

## What each file does

| File | Purpose |
| --- | --- |
| `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `requirements.lock.txt`, `.env.example` | Environment (secrets are placeholders) |
| `mobile_money_generator.py` | Supplied generator, unchanged |
| `check_env.py` | Versions, hardware, memory settings |
| `capture.py` | Streams the five generator streams to CSV with audit totals |
| `sql/01_tables.sql` to `sql/04_checks.sql` | PostgreSQL tables, bulk load, constraints and indexes, checks |
| `prepare_import.py`, `neo4j_setup.py`, `neo4j_checks.py` | Neo4j import files, constraints and index, checks |
| `db.py` | `run_pg` / `run_neo` helpers and result normalisation |
| `queries.py` | Every SQL/Cypher pair for Q1 to Q7, review sets, the improved Q7 SQL |
| `trace_account.py` | Section 3.3 trace in both models |
| `phase4.py`, `phase5.py` | Q1 to Q7 runs, outputs and charts |
| `cases.py`, `compare.py`, `csv_checks.py` | The 61-case comparison and independent CSV checks |
| `benchmark.py`, `plans.py`, `bench_report.py` | Timing, query plans, timing summary |
| `loadtest.py`, `load_report.py` | Concurrent load test and scaling plots |

## Outputs

- `logs/`: full console output of every run.
- `results/`: CSV and JSON outputs of every question, the 61-case outputs (`compare/`, `compare_improved/`), raw and summarised timings (`bench_raw_*.csv`, `bench_summary_*.csv`), load-test requests and repetitions (`load_raw_*.csv`, `load_reps_*.csv`, `load_summary_*.csv`), query plans (`plans/`) and charts (`*.png`).
- `data/capture_audit.json`: capture counts, sizes and audit totals. The CSVs in `data/` and both database stores stay local and are not in the repository.
