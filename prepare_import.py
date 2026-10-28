"""Section 3.2 — make temporary Neo4j import copies of the captured CSVs.
Source CSVs in data/ are only read, never modified. Copies go to import/.
Run: docker compose run --rm app python prepare_import.py
"""
import csv
import os
import shutil
import time

SRC, DST = "data", "import"

# (source file, import file, Neo4j typed header replacing the source header)
RETYPED = [
    ("customers.csv", "customers.csv",
     "customer_id:ID(Customer),region:string"),
    ("accounts.csv", "accounts.csv",
     "account_id:ID(Account),:IGNORE,role:string"),          # customer_id -> owns.csv
    ("devices.csv", "devices.csv",
     "device_id:ID(Device),access_type:string"),
    ("account_devices.csv", "used_device.csv",
     ":START_ID(Account),:END_ID(Device),first_day:int,last_day:int,observations:int"),
    ("transfers.csv", "transfers.csv",
     "transfer_id:long,:START_ID(Account),:END_ID(Account),occurred_at:long,amount_rwf:int"),
]


def retype(src, dst, header):
    """Copy a CSV, swapping only its header line. Streams bytes, so 0.8 GB is fine."""
    with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
        fin.readline()                      # drop the original header
        fout.write(header + "\r\n")         # csv.DictWriter used \r\n, so stay consistent
        shutil.copyfileobj(fin, fout, 16 * 1024 * 1024)


def derive_owns(src, dst):
    """owns.csv: one OWNS relationship per account, columns customer_id, account_id,
    rows sorted by (customer_id, account_id). 248,000 rows is small enough to sort in memory."""
    with open(src, newline="") as fin:
        reader = csv.DictReader(fin)
        pairs = sorted((int(r["customer_id"]), int(r["account_id"])) for r in reader)
    with open(dst, "w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow([":START_ID(Customer)", ":END_ID(Account)"])
        writer.writerows(pairs)
    return len(pairs)


def main():
    os.makedirs(DST, exist_ok=True)
    t0 = time.perf_counter()
    for src_name, dst_name, header in RETYPED:
        src, dst = os.path.join(SRC, src_name), os.path.join(DST, dst_name)
        retype(src, dst, header)
        print(f"{src_name:20} -> {dst_name:18} header: {header}")
    n = derive_owns(os.path.join(SRC, "accounts.csv"), os.path.join(DST, "owns.csv"))
    print(f"{'accounts.csv':20} -> {'owns.csv':18} {n:,} rows, header: :START_ID(Customer),:END_ID(Account)")
    print(f"\nPrepared in {time.perf_counter() - t0:.1f} s")

    print("\nImport copies:")
    for name in sorted(os.listdir(DST)):
        if name.endswith(".csv"):
            path = os.path.join(DST, name)
            with open(path) as f:
                first = f.readline().strip()
            print(f"  {name:18} {os.path.getsize(path) / 1e9:7.3f} GB   {first}")


if __name__ == "__main__":
    main()
