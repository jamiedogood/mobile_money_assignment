-- Sections 2.1 + 2.2 step 2 — keys, foreign keys, CHECKs, indexes, ANALYZE.
-- Every ADD CONSTRAINT here validates against the loaded rows (fails if any row breaks it).
\timing on
SELECT clock_timestamp() AS setup_start \gset

-- Primary keys
ALTER TABLE customers       ADD CONSTRAINT customers_pk       PRIMARY KEY (customer_id);
ALTER TABLE devices         ADD CONSTRAINT devices_pk         PRIMARY KEY (device_id);
ALTER TABLE accounts        ADD CONSTRAINT accounts_pk        PRIMARY KEY (account_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_pk PRIMARY KEY (account_id, device_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_pk       PRIMARY KEY (transfer_id);

-- Foreign keys: ownership, device use, both transfer endpoints
ALTER TABLE accounts        ADD CONSTRAINT accounts_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_account_fk
    FOREIGN KEY (account_id)  REFERENCES accounts (account_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_device_fk
    FOREIGN KEY (device_id)   REFERENCES devices (device_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_sender_fk
    FOREIGN KEY (sender_id)   REFERENCES accounts (account_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_receiver_fk
    FOREIGN KEY (receiver_id) REFERENCES accounts (account_id);

-- Value rules required by the brief
ALTER TABLE transfers       ADD CONSTRAINT transfers_amount_positive   CHECK (amount_rwf > 0);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_obs_positive CHECK (observations > 0);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_day_range
    CHECK (0 <= first_day AND first_day <= last_day AND last_day <= 29);

-- Category rules (extra, documents the allowed values)
ALTER TABLE accounts  ADD CONSTRAINT accounts_role_valid
    CHECK (role IN ('person', 'merchant', 'agent'));
ALTER TABLE devices   ADD CONSTRAINT devices_access_type_valid
    CHECK (access_type IN ('handset', 'public_terminal'));
ALTER TABLE customers ADD CONSTRAINT customers_region_valid
    CHECK (region IN ('Kigali', 'Northern', 'Southern', 'Eastern', 'Western'));

-- Secondary indexes from the brief
CREATE INDEX accounts_customer_idx       ON accounts (customer_id, account_id);
CREATE INDEX account_devices_device_idx  ON account_devices (device_id, account_id);
CREATE INDEX transfers_sender_time_idx   ON transfers (sender_id, occurred_at)
    INCLUDE (receiver_id, amount_rwf, transfer_id);
CREATE INDEX transfers_receiver_time_idx ON transfers (receiver_id, occurred_at)
    INCLUDE (sender_id, amount_rwf, transfer_id);
CREATE INDEX transfers_time_brin         ON transfers USING brin (occurred_at);

ANALYZE;

SELECT round(extract(epoch FROM clock_timestamp() - :'setup_start'::timestamptz)::numeric, 2)
       AS total_setup_seconds;
