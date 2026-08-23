#!/usr/bin/env python3
"""
post_scan_recovery.py
-----------------------
CPEN 315/733 - Project 7: Cache Politics - Group 2, Topic 7

Week 3 deliverable: the post-scan hit-rate recovery plot.

For each policy, dumps a per-access hit(1)/miss(0) trace from cache_sim
on the scan-heavy trace (--dump-hits), then computes a sliding-window
hit rate over the accesses that occur *after* the one-time audit scan
ends (the point recorded in the trace file's header comment as
post_scan_start_index). This is the plot that makes ARC's "recovers
faster than LRU after a scan" claim visible and measurable rather than
just a hit-rate-table number.

Usage:
    python3 post_scan_recovery.py --sim ../src/cache_sim \
        --trace ../traces/ssnit_seed2_scan.trace \
        --size 1024 --assoc 4 --block 64 --out-dir ../results \
        --window 200
"""
import argparse
import subprocess
import re
import os


def find_post_scan_start(trace_path):
    with open(trace_path) as f:
        for line in f:
            if line.startswith("#"):
                m = re.search(r"post_scan_start_index=(\d+)", line)
                if m:
                    return int(m.group(1))
    raise ValueError(f"{trace_path} has no '# ... post_scan_start_index=N' header comment. "
                      "Regenerate it with gen_ssnit_trace.py (scan variant).")


def windowed_hit_rate(hit_string, start_idx, window):
    """Returns (x, y) where x[i] = accesses-since-scan-ended at the start
    of window i, y[i] = hit rate within that window."""
    tail = hit_string[start_idx:]
    xs, ys = [], []
    for i in range(0, len(tail) - window + 1, window):
        chunk = tail[i:i + window]
        hr = chunk.count("1") / len(chunk)
        xs.append(i)
        ys.append(hr)
    return xs, ys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sim", default="../src/cache_sim")
    ap.add_argument("--trace", default="../traces/ssnit_seed2_scan.trace")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--assoc", type=int, default=4)
    ap.add_argument("--block", type=int, default=64)
    ap.add_argument("--window", type=int, default=200,
                     help="accesses per sliding window for the recovery curve")
    ap.add_argument("--out-dir", default="../results")
    ap.add_argument("--policies", nargs="+", default=["lru", "fifo", "random", "arc", "opt"])
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    start_idx = find_post_scan_start(args.trace)
    print(f"Scan ends / working-set return begins at access #{start_idx}")

    curves = {}
    for policy in args.policies:
        dump_path = f"{args.out_dir}/_tmp_hits_{policy}.txt"
        subprocess.run(
            [args.sim, "--policy", policy, "--size", str(args.size), "--assoc", str(args.assoc),
             "--block", str(args.block), "--trace", args.trace, "--dump-hits", dump_path,
             "--label", f"recovery_{policy}"],
            capture_output=True, text=True, check=True)
        with open(dump_path) as f:
            hit_string = f.read().strip()
        os.remove(dump_path)
        xs, ys = windowed_hit_rate(hit_string, start_idx, args.window)
        curves[policy] = (xs, ys)
        print(f"{policy.upper():6s}: first post-scan window hit rate = {ys[0]:.3f}, "
              f"steady-state (last window) = {ys[-1]:.3f}")

    # write CSV
    csv_path = f"{args.out_dir}/post_scan_recovery.csv"
    with open(csv_path, "w") as f:
        f.write("policy,accesses_since_scan_end,hit_rate\n")
        for policy, (xs, ys) in curves.items():
            for x, y in zip(xs, ys):
                f.write(f"{policy},{x},{y:.6f}\n")
    print(f"Wrote {csv_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        for policy, (xs, ys) in curves.items():
            ax.plot(xs, ys, marker="o", markersize=3, label=policy.upper())
        ax.set_xlabel(f"Accesses since scan ended (window = {args.window})")
        ax.set_ylabel("Hit rate within window")
        ax.set_title(f"Post-scan hit-rate recovery (cache={args.size}B, assoc={args.assoc})")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        out_png = f"{args.out_dir}/post_scan_recovery.png"
        fig.savefig(out_png, dpi=150)
        print(f"Wrote {out_png}")
    except ImportError:
        print("matplotlib not available -- CSV written, skipping plot.")


if __name__ == "__main__":
    main()
