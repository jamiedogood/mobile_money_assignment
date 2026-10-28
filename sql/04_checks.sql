-- Section 2.2 step 3 — counts, audit totals, roles, constraints, indexes, sizes.
-- Expected values come from capture.py (data/capture_audit.json).
\pset footer off

\echo '=== Row counts vs capture.py ==='
SELECT t.tbl, t.n AS loaded, e.expected, t.n = e.expected AS ok
FROM (
          SELECT 'customers' AS tbl, count(*) AS n FROM customers
    UNION ALL SELECT 'accounts',        count(*) FROM accounts
    UNION ALL SELECT 'devices',         count(*) FROM devices
    UNION ALL SELECT 'account_devices', count(*) FROM account_devices
    UNION ALL SELECT 'transfers',       count(*) FROM transfers
) t
JOIN (VALUES ('customers', 228000), ('accounts', 248000), ('devices', 228600),
             ('account_devices', 285600), ('transfers', 20003300)) e(tbl, expected)
  USING (tbl)
ORDER BY t.tbl;

\echo '=== Transfer audit totals vs capture.py ==='
SELECT count(*)                         AS transfer_count,
       min(occurred_at)                 AS earliest,
       max(occurred_at)                 AS latest,
       sum(amount_rwf)                  AS sum_amount_rwf,
       to_timestamp(min(occurred_at))   AS earliest_cat,
       to_timestamp(max(occurred_at))   AS latest_cat,
       (count(*) = 20003300
        AND min(occurred_at) = 1788235200
        AND max(occurred_at) = 1790798399
        AND sum(amount_rwf) = 231482327870) AS audit_ok
FROM transfers;

\echo '=== Account roles (expect 240000 person, 6000 merchant, 2000 agent) ==='
SELECT role, count(*) FROM accounts GROUP BY role ORDER BY role;

\echo '=== Constraints (convalidated = t means checked against every loaded row) ==='
SELECT conrelid::regclass AS table_name, conname, contype, convalidated,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY 1, 2;

\echo '=== Indexes ==='
SELECT tablename, indexname, indexdef FROM pg_indexes
WHERE schemaname = 'public' ORDER BY tablename, indexname;

\echo '=== Sizes (1 GB = 1,000,000,000 bytes) ==='
SELECT c.relname AS table_name,
       round(pg_table_size(c.oid)   / 1e9, 3) AS data_gb,
       round(pg_indexes_size(c.oid) / 1e9, 3) AS index_gb,
       round(pg_total_relation_size(c.oid) / 1e9, 3) AS total_gb
FROM pg_class c
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
ORDER BY total_gb DESC;

SELECT round(sum(pg_table_size(c.oid))   / 1e9, 3) AS all_data_gb,
       round(sum(pg_indexes_size(c.oid)) / 1e9, 3) AS all_index_gb,
       round(pg_database_size(current_database()) / 1e9, 3) AS database_gb
FROM pg_class c
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r';

SHOW timezone;
