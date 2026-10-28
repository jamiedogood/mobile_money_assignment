"""Section 7.2 — throughput and p95 versus client count, both engines and workloads.
Run (no database needed): docker compose run --rm app python load_report.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = []
for engine in ("pg", "neo"):
    path = f"results/load_summary_{engine}.csv"
    if os.path.exists(path):
        with open(path, newline="") as f:
            rows += list(csv.DictReader(f))

names = {"pg": "PostgreSQL", "neo": "Neo4j"}
colors = {"pg": "#3b6ea5", "neo": "#c0504d"}
workloads = sorted({r["workload"] for r in rows})

fig, axes = plt.subplots(2, len(workloads), figsize=(6 * len(workloads), 8.5), squeeze=False)
for j, wl in enumerate(workloads):
    for engine in ("pg", "neo"):
        data = sorted((int(r["clients"]), float(r["throughput_rps"]), float(r["p95_ms"]))
                      for r in rows if r["workload"] == wl and r["engine"] == engine)
        if not data:
            continue
        x = [d[0] for d in data]
        axes[0][j].plot(x, [d[1] for d in data], marker="o", color=colors[engine], label=names[engine])
        axes[1][j].plot(x, [d[2] for d in data], marker="o", color=colors[engine], label=names[engine])
    axes[0][j].set_title(f"{wl}: throughput")
    axes[0][j].set_ylabel("Correct requests per second")
    axes[1][j].set_title(f"{wl}: p95 latency")
    axes[1][j].set_ylabel("p95 latency (ms)")
    for i in (0, 1):
        axes[i][j].set_xlabel("Concurrent clients")
        axes[i][j].set_xticks([1, 4, 8, 16])
        axes[i][j].grid(alpha=0.3)
        axes[i][j].legend()
fig.suptitle("Section 7 concurrency (median of 3 repetitions, 15 s window)")
fig.tight_layout()
fig.savefig("results/load_scaling.png", dpi=150)

print(f"{'workload':8} {'engine':10} {'thr@1':>8} {'thr@16':>8} {'x':>6} {'p95@1':>9} {'p95@16':>9} {'x':>6}")
for wl in workloads:
    for engine in ("pg", "neo"):
        d = {int(r["clients"]): r for r in rows if r["workload"] == wl and r["engine"] == engine}
        if 1 in d and 16 in d:
            t1, t16 = float(d[1]["throughput_rps"]), float(d[16]["throughput_rps"])
            p1, p16 = float(d[1]["p95_ms"]), float(d[16]["p95_ms"])
            print(f"{wl:8} {names[engine]:10} {t1:>8.1f} {t16:>8.1f} {t16 / t1:>6.2f} "
                  f"{p1:>9.1f} {p16:>9.1f} {p16 / p1:>6.2f}")
print("\nChart saved: results/load_scaling.png")
