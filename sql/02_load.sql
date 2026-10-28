-- Section 2.2 step 1 — bulk-load the captured CSVs (parents before children).
-- \timing prints each \copy; the final SELECT gives total loading seconds.
\timing on
SELECT clock_timestamp() AS load_start \gset

\copy customers       FROM '/data/customers.csv'       CSV HEADER
\copy devices         FROM '/data/devices.csv'         CSV HEADER
\copy accounts        FROM '/data/accounts.csv'        CSV HEADER
\copy account_devices FROM '/data/account_devices.csv' CSV HEADER
\copy transfers       FROM '/data/transfers.csv'       CSV HEADER

SELECT round(extract(epoch FROM clock_timestamp() - :'load_start'::timestamptz)::numeric, 2)
       AS total_load_seconds;
