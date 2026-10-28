"""Section 1.2 — capture the five generator streams to CSV, streaming (never in memory).
Run: docker compose run --rm app python capture.py            # preview + full capture
     docker compose run --rm app python capture.py --preview  # preview only
Outputs: data/<stream>.csv and data/capture_audit.json (used later for checks).
"""
import csv
import hashlib
import json
import os
import sys
import time
from itertools import islice

import mobile_money_generator as g

OUT = "data"
STREAMS = ["customers", "accounts", "devices", "account_devices", "transfers"]
EXPECTED = g.dataset_info()["expected_counts"]


def preview():
    print("dataset_info():")
    print(json.dumps(g.dataset_info(), indent=2))
    print("\nFIELDS:", g.FIELDS)
    for stream in STREAMS:
        print(f"\n--- {stream}: first 10 ---")
        # A fresh iter_<stream>() call restarts the stream, so this doesn't affect capture.
        for row in islice(getattr(g, f"iter_{stream}")(), 10):
            print(row)


def capture(stream):
    path = os.path.join(OUT, f"{stream}.csv")
    consumed = written = 0
    is_transfers = stream == "transfers"
    min_ts, max_ts, total_amount = None, None, 0

    t0 = time.perf_counter()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=g.FIELDS[stream])
        writer.writeheader()
        for row in getattr(g, f"iter_{stream}")():
            consumed += 1
            writer.writerow(row)
            written += 1
            if is_transfers:
                ts = row["occurred_at"]
                # Transfers are NOT time-sorted, so track min/max explicitly.
                if min_ts is None or ts < min_ts:
                    min_ts = ts
                if max_ts is None or ts > max_ts:
                    max_ts = ts
                total_amount += row["amount_rwf"]
                if written % 1_000_000 == 0:
                    print(f"  transfers: {written:,} rows "
                          f"({time.perf_counter() - t0:,.1f} s)", flush=True)
    seconds = time.perf_counter() - t0

    result = dict(stream=stream, consumed=consumed, written=written,
                  expected=EXPECTED[stream], match=(written == EXPECTED[stream]),
                  seconds=round(seconds, 2), csv_bytes=os.path.getsize(path),
                  csv_gb=round(os.path.getsize(path) / 1e9, 3))
    if is_transfers:
        result.update(transfer_count=written, earliest_occurred_at=min_ts,
                      latest_occurred_at=max_ts, sum_amount_rwf=total_amount)
    return result


def main():
    preview()
    if "--preview" in sys.argv:
        return

    os.makedirs(OUT, exist_ok=True)
    with open("mobile_money_generator.py", "rb") as f:
        generator_sha256 = hashlib.sha256(f.read()).hexdigest()

    results = []
    overall = time.perf_counter()
    for stream in STREAMS:
        print(f"\nCapturing {stream} ...", flush=True)
        results.append(capture(stream))
        print("  ->", results[-1])
    total_seconds = time.perf_counter() - overall

    print("\n==================== CAPTURE SUMMARY ====================")
    print(f"{'stream':16}{'written':>12}{'expected':>12}{'ok':>5}{'seconds':>10}{'CSV GB':>9}")
    for r in results:
        print(f"{r['stream']:16}{r['written']:>12,}{r['expected']:>12,}"
              f"{'yes' if r['match'] else 'NO':>5}{r['seconds']:>10.1f}{r['csv_gb']:>9.3f}")
    total_rows = sum(r["written"] for r in results)
    print(f"{'TOTAL':16}{total_rows:>12,}{20_993_500:>12,}"
          f"{'yes' if total_rows == 20_993_500 else 'NO':>5}{total_seconds:>10.1f}")
    t = results[-1]
    print(f"\nTransfer audit: count={t['transfer_count']:,}  "
          f"earliest={t['earliest_occurred_at']}  latest={t['latest_occurred_at']}  "
          f"sum_amount_rwf={t['sum_amount_rwf']:,}")
    print("Generator SHA-256:", generator_sha256)

    with open(os.path.join(OUT, "capture_audit.json"), "w") as f:
        json.dump(dict(generator_sha256=generator_sha256,
                       total_seconds=round(total_seconds, 2), streams=results), f, indent=2)


if __name__ == "__main__":
    main()
