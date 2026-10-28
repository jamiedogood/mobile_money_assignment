"""Section 6.1 — independent checks against the captured CSVs, in plain Python (no database).
1. Recompute Q3 for set A from data/account_devices.csv and compare with the database result.
2. Re-check the set A cycle (Q6) and its first three steps as a chain (Q5) from data/transfers.csv.
Run: docker compose run --rm app python csv_checks.py     (after phase4 q3, phase5 q5 and q6)
"""
import ast
import csv
from time import perf_counter

from queries import SETS, hour_window

ok_all = True


def check(label, cond):
    global ok_all
    ok_all &= bool(cond)
    print(f"  [{'ok' if cond else 'FAIL'}] {label}")


# ------------------------------------------------------------ 1. Q3 device overlap, set A
A = SETS["A"]["account"]
print(f"=== 1. Q3 shared devices for account {A}, recomputed from account_devices.csv ===")
with open("data/account_devices.csv", newline="") as f:
    rows = [tuple(int(v) for v in r) for r in csv.reader(f) if r[0] != "account_id"]
mine = [r for r in rows if r[0] == A]
print(f"  raw CSV rows for account {A}: {mine}")
my_devices = {r[1]: r for r in mine}
computed = set()
for acct, dev, first, last, obs in rows:
    if dev in my_devices and acct != A:
        _, _, f0, l0, _ = my_devices[dev]
        start, end = max(f0, first), min(l0, last)
        if start <= end:
            computed.add((acct, dev, start, end))

with open("results/q3_A.csv", newline="") as f:
    db = {(int(r["other_account"]), int(r["device_id"]), int(r["overlap_start"]),
           int(r["overlap_end"])) for r in csv.DictReader(f)}
check(f"CSV recomputation gives {len(computed)} overlaps, database gave {len(db)}", computed == db)

# One overlap shown in full, with both raw CSV rows
other, dev, start, end = sorted(computed)[0]
other_row = next(r for r in rows if r[0] == other and r[1] == dev)
print(f"  example: account {A} row {my_devices[dev]}  and account {other} row {other_row}")
print(f"           overlap = [max({my_devices[dev][2]},{other_row[2]}), "
      f"min({my_devices[dev][3]},{other_row[3]})] = [{start},{end}]")
check("example overlap satisfies max(first_day) <= min(last_day)", start <= end)

# ------------------------------------------------------------ 2. Q6 cycle + Q5 chain, set A
print("\n=== 2. Set A cycle (Q6) and chain (Q5), re-checked from transfers.csv ===")
with open("results/q6_A.csv", newline="") as f:
    cycle_ids = list(ast.literal_eval(next(csv.DictReader(f))["transfer_ids"]))
with open("results/q5_A.csv", newline="") as f:
    r = next(csv.DictReader(f))
    chain_ids = [int(r["first_id"]), int(r["second_id"]), int(r["third_id"])]
wanted = {str(i) for i in cycle_ids + chain_ids}

t0 = perf_counter()
found = {}
with open("data/transfers.csv") as f:
    next(f)
    for line in f:                                 # stream: never load 20M rows
        tid = line.split(",", 1)[0]
        if tid in wanted:
            found[int(tid)] = tuple(int(v) for v in line.strip().split(","))
            if len(found) == len(wanted):
                break
print(f"  scanned transfers.csv in {perf_counter() - t0:.1f} s, found {len(found)}/{len(wanted)} rows")
for tid in cycle_ids:
    print(f"    {found[tid]}   (transfer_id, sender, receiver, occurred_at, amount_rwf)")

start, end = hour_window(SETS["A"]["day"])
cyc = [found[i] for i in cycle_ids]
check(f"cycle length {len(cyc)} is between 3 and 8", 3 <= len(cyc) <= 8)
check("cycle starts and ends at the review account", cyc[0][1] == A and cyc[-1][2] == A)
check("each transfer leaves from where the previous arrived",
      all(cyc[i][2] == cyc[i + 1][1] for i in range(len(cyc) - 1)))
check("no return to the start before the end (stop at first return)",
      all(t[2] != A for t in cyc[:-1]))
check("all events inside 09:45-10:45 CAT", all(start <= t[3] < end for t in cyc))
check("strictly increasing times", all(cyc[i][3] < cyc[i + 1][3] for i in range(len(cyc) - 1)))
check("span at most 1,800 s", cyc[-1][3] - cyc[0][3] <= 1800)
check("amount rule 90*prev <= 100*next <= 105*prev",
      all(90 * cyc[i][4] <= 100 * cyc[i + 1][4] <= 105 * cyc[i][4] for i in range(len(cyc) - 1)))

ch = [found[i] for i in chain_ids]
check("chain: first transfer from review account inside the hour",
      ch[0][1] == A and start <= ch[0][3] < end)
check("chain: linked receiver -> sender", ch[0][2] == ch[1][1] and ch[1][2] == ch[2][1])
check("chain: each gap > 0 and <= 600 s",
      all(0 < ch[i + 1][3] - ch[i][3] <= 600 for i in range(2)))
check("chain: four distinct accounts", len({ch[0][1], ch[0][2], ch[1][2], ch[2][2]}) == 4)
check("chain: amount rule",
      all(90 * ch[i][4] <= 100 * ch[i + 1][4] <= 105 * ch[i][4] for i in range(2)))

print("\nALL CSV CHECKS PASSED" if ok_all else "\nSOME CSV CHECKS FAILED")
