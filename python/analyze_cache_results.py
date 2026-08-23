#!/usr/bin/env python3
"""
analyze_cache_results.py
--------------------------
CPEN 315/733 - Project 7: Cache Politics - Group 2, Topic 7

Runs cache_sim across the required experiment matrix (policy x trace
type x cache size), collects results, writes a summary CSV/table, and
produces the required plots:
  - hit-rate bar chart (policy x trace type, at the default cache size)
  - AMAT comparison bar chart
  - hit-rate vs cache size line chart, per policy, per trace type

Usage:
    python3 analyze_cache_results.py \
        --sim ../src/cache_sim \
        --trace-dir ../traces --seed 2 --label ssnit \
        --out-dir ../results
"""
import argparse
import subprocess
import re
import os
import csv

POLICIES = ["lru", "fifo", "random", "arc"]
TRACE_TYPES = ["recency", "scan"]


def run_sim(sim_bin, policy, size, assoc, block, trace_path, hit_time, miss_penalty, label):
    result = subprocess.run(
        [sim_bin, "--policy", policy, "--size", str(size), "--assoc", str(assoc),
         "--block", str(block), "--trace", trace_path,
         "--hit-time", str(hit_time), "--miss-penalty", str(miss_penalty),
         "--label", label],
        capture_output=True, text=True, check=True)
    out = result.stdout
    def grab(key, cast=float):
        return cast(re.search(rf"{key}=([\d.]+)", out).group(1))
    return {
        "policy": policy,
        "hits": int(grab("hits", int)),
        "misses": int(grab("misses", int)),
        "hit_rate": grab("hit_rate"),
        "amat": grab("amat"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", default="../src/cache_sim")
    ap.add_argument("--trace-dir", default="../traces")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--label", default="ssnit")
    ap.add_argument("--out-dir", default="../results")
    ap.add_argument("--block", type=int, default=64)
    ap.add_argument("--assoc", type=int, default=4)
    ap.add_argument("--sizes", type=int, nargs="+", default=[512, 1024, 2048],
                     help="cache sizes (bytes) to sweep -- 3 sizes required")
    ap.add_argument("--hit-time", type=float, default=1.0)
    ap.add_argument("--miss-penalty", type=float, default=100.0)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    rows = []
    for trace_type in TRACE_TYPES:
        trace_path = f"{args.trace_dir}/{args.label}_seed{args.seed}_{trace_type}.trace"
        for size in args.sizes:
            for policy in POLICIES:
                r = run_sim(args.sim, policy, size, args.assoc, args.block, trace_path,
                            args.hit_time, args.miss_penalty,
                            f"{trace_type}_{policy}_{size}")
                r.update({"trace_type": trace_type, "cache_size": size})
                rows.append(r)

    csv_path = f"{args.out_dir}/experiment_matrix.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trace_type", "cache_size", "policy",
                                           "hits", "misses", "hit_rate", "amat"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {csv_path} ({len(rows)} rows)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        default_size = args.sizes[len(args.sizes) // 2]

        # --- Hit-rate bar chart at the default (middle) cache size ---
        fig, ax = plt.subplots(figsize=(7, 4.5))
        x = np.arange(len(TRACE_TYPES))
        width = 0.2
        for i, policy in enumerate(POLICIES):
            vals = [next(r["hit_rate"] for r in rows
                         if r["policy"] == policy and r["trace_type"] == t
                         and r["cache_size"] == default_size) for t in TRACE_TYPES]
            ax.bar(x + i * width, vals, width, label=policy.upper())
        ax.set_xticks(x + 1.5 * width)
        ax.set_xticklabels(["Recency-heavy", "Scan-heavy"])
        ax.set_ylabel("Hit rate")
        ax.set_title(f"Hit rate by policy and trace type (cache={default_size}B)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(f"{args.out_dir}/hit_rate_by_policy.png", dpi=150)
        print(f"Wrote {args.out_dir}/hit_rate_by_policy.png")

        # --- AMAT bar chart ---
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for i, policy in enumerate(POLICIES):
            vals = [next(r["amat"] for r in rows
                         if r["policy"] == policy and r["trace_type"] == t
                         and r["cache_size"] == default_size) for t in TRACE_TYPES]
            ax.bar(x + i * width, vals, width, label=policy.upper())
        ax.set_xticks(x + 1.5 * width)
        ax.set_xticklabels(["Recency-heavy", "Scan-heavy"])
        ax.set_ylabel("AMAT (cycles)")
        ax.set_title(f"AMAT by policy and trace type (cache={default_size}B)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(f"{args.out_dir}/amat_by_policy.png", dpi=150)
        print(f"Wrote {args.out_dir}/amat_by_policy.png")

        # --- Hit rate vs cache size, per policy, scan-heavy trace ---
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for policy in POLICIES:
            vals = [next(r["hit_rate"] for r in rows
                         if r["policy"] == policy and r["trace_type"] == "scan"
                         and r["cache_size"] == s) for s in args.sizes]
            ax.plot(args.sizes, vals, marker="o", label=policy.upper())
        ax.set_xlabel("Cache size (bytes)")
        ax.set_ylabel("Hit rate")
        ax.set_title("Scan-heavy trace: hit rate vs. cache size")
        ax.legend()
        fig.tight_layout()
        fig.savefig(f"{args.out_dir}/hitrate_vs_cachesize_scan.png", dpi=150)
        print(f"Wrote {args.out_dir}/hitrate_vs_cachesize_scan.png")

    except ImportError:
        print("matplotlib not available -- CSV written, skipping plots.")


if __name__ == "__main__":
    main()
