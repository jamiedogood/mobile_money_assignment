"""Section 6.2/6.3 — combine benchmark summaries: medians, min/max, PG/Neo4j median ratio, chart.
Run (no database needed): docker compose run --rm app python bench_report.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(name):
    path = f"results/bench_summary_{name}.csv"
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {r["case"]: r for r in csv.DictReader(f)}


pg, neo, pg_imp = load("pg"), load("neo"), load("pg_improved")
order = list(pg or neo)


def med(r):
    return float(r["median_ms"]) if r and r.get("median_ms") else None


def cell(r):
    if not r:
        return f"{'-':>32}"
    if not r.get("median_ms"):
        return f"{'timeout ' + r['timeouts'] + ' / error ' + r['errors']:>32}"
    return f"{float(r['median_ms']):>10,.1f} [{float(r['min_ms']):>8,.1f}-{float(r['max_ms']):>9,.1f}]"


print(f"{'case':10} {'PostgreSQL median [min-max] ms':>32} {'Neo4j median [min-max] ms':>32} {'PG/Neo':>8}"
      + (f" {'PG improved median ms':>32} {'imp/Neo':>8}" if pg_imp else ""))
rows_out = []
for c in order:
    p, n, i = pg.get(c), neo.get(c), pg_imp.get(c)
    ratio = med(p) / med(n) if med(p) and med(n) else None
    line = f"{c:10} {cell(p)} {cell(n)} {(f'{ratio:8.2f}' if ratio else '     n/a')}"
    imp_ratio = None
    if pg_imp:
        imp_ratio = med(i) / med(n) if med(i) and med(n) else None
        line += f" {cell(i)} {(f'{imp_ratio:8.2f}' if imp_ratio else '        ')}"
    print(line)
    rows_out.append(dict(case=c, pg_median_ms=med(p), neo_median_ms=med(n),
                         pg_neo_ratio=round(ratio, 3) if ratio else "",
                         pg_improved_median_ms=med(i), improved_neo_ratio=round(imp_ratio, 3) if imp_ratio else ""))

with open("results/bench_report.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0]))
    w.writeheader()
    w.writerows(rows_out)

# Chart: medians per case, log scale (values span from ms to tens of seconds)
fig, ax = plt.subplots(figsize=(13, 6))
x = range(len(order))
width = 0.27 if pg_imp else 0.4
series = [("PostgreSQL", pg, "#3b6ea5"), ("Neo4j", neo, "#c0504d")]
if pg_imp:
    series.append(("PostgreSQL improved Q7", pg_imp, "#6aa84f"))
for k, (label, data, color) in enumerate(series):
    vals = [med(data.get(c)) or 0 for c in order]
    ax.bar([xi + (k - (len(series) - 1) / 2) * width for xi in x], vals, width, label=label, color=color)
ax.set_yscale("log")
ax.set_ylabel("Median latency (ms, log scale)")
ax.set_xticks(list(x))
ax.set_xticklabels(order, rotation=60, ha="right")
ax.set_title("Median query latency per case (5 measured runs; missing bar = timeout)")
ax.grid(axis="y", alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig("results/bench_medians.png", dpi=150)
print("\nSaved results/bench_report.csv and results/bench_medians.png")
