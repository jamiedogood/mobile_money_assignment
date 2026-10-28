-- Section 2.1 — the five tables (columns + NOT NULL only).
-- Keys, foreign keys and CHECKs are added AFTER loading in 03_constraints_indexes.sql,
-- because bulk-loading into unindexed, unconstrained tables is much faster.
-- Re-runnable: drops existing tables first.

DROP TABLE IF EXISTS transfers, account_devices, accounts, devices, customers CASCADE;

CREATE TABLE customers (
    customer_id  INTEGER NOT NULL,          -- customer identifier (no names/ID docs in data)
    region       TEXT    NOT NULL           -- Kigali | Northern | Southern | Eastern | Western
);

CREATE TABLE devices (
    device_id    INTEGER NOT NULL,          -- device identifier
    access_type  TEXT    NOT NULL           -- handset | public_terminal
);

CREATE TABLE accounts (
    account_id   INTEGER NOT NULL,          -- wallet identifier
    customer_id  INTEGER NOT NULL,          -- owning customer
    role         TEXT    NOT NULL           -- person | merchant | agent
);

CREATE TABLE account_devices (
    account_id   INTEGER  NOT NULL,         -- wallet observed on the device
    device_id    INTEGER  NOT NULL,         -- device it was observed on
    first_day    SMALLINT NOT NULL,         -- first observed day, 0 = 1 Sep 2026 (inclusive)
    last_day     SMALLINT NOT NULL,         -- last observed day, 29 = 30 Sep 2026 (inclusive)
    observations INTEGER  NOT NULL          -- number of observations within that interval
);

CREATE TABLE transfers (
    transfer_id  BIGINT  NOT NULL,          -- unique event identifier
    sender_id    INTEGER NOT NULL,          -- paying wallet
    receiver_id  INTEGER NOT NULL,          -- receiving wallet
    occurred_at  BIGINT  NOT NULL,          -- Unix time, seconds (UTC epoch; display in CAT)
    amount_rwf   INTEGER NOT NULL           -- whole Rwandan francs
);

\d+ customers
\d+ devices
\d+ accounts
\d+ account_devices
\d+ transfers
