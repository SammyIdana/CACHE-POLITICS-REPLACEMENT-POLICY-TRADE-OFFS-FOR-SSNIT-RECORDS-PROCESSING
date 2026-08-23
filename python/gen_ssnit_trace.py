#!/usr/bin/env python3
"""
gen_ssnit_trace.py
-------------------
CPEN 315/733 - Project 7: Cache Politics
Group 2 - Topic 7

Generates a pair of seeded, synthetic SSNIT-records-processing memory
access traces used to evaluate the cache_sim replacement policies:

  1. <label>_recency.trace  - steady-state access to a small "hot" working
     set of active-contributor records (repeated, recency-friendly).
  2. <label>_scan.trace     - the same hot working set, interrupted by a
     one-time full-table pension-audit sweep, then a return to the
     working set (the pattern ARC is specifically designed to survive
     and plain LRU is not).

Addresses are emitted as decimal byte addresses, one per line, sized to
a configurable "record size" so consecutive records fall in different
cache blocks.

Every team receives a *different* trace from a *different* seed, per
the course integrity framework (Part I S7 of the project portfolio).
"""

import argparse
import random


def gen_recency_trace(rng, working_set_records, record_size, repeats, hot_bias=0.85):
    """Repeated access to a hot working set, mild locality skew."""
    addrs = []
    base_addrs = [r * record_size for r in range(working_set_records)]
    hot_count = max(1, working_set_records // 5)  # top 20% of records are "active contributors"
    hot_addrs = base_addrs[:hot_count]
    for _ in range(repeats):
        if rng.random() < hot_bias:
            addrs.append(rng.choice(hot_addrs))
        else:
            addrs.append(rng.choice(base_addrs))
    return addrs


def gen_scan_trace(rng, working_set_records, record_size, pre_repeats, scan_records,
                    post_repeats, hot_bias=0.85):
    """Working-set warm-up, then a single full-table scan, then a return
    to the working set. scan_records should exceed the cache capacity
    (in records) to actually expose the LRU scan-pollution pathology --
    the caller is responsible for choosing scan_records large enough
    relative to the cache configuration under test."""
    addrs = []
    base_addrs = [r * record_size for r in range(working_set_records)]
    hot_count = max(1, working_set_records // 5)
    hot_addrs = base_addrs[:hot_count]

    # Phase 1: warm-up on the working set (recency-heavy)
    for _ in range(pre_repeats):
        if rng.random() < hot_bias:
            addrs.append(rng.choice(hot_addrs))
        else:
            addrs.append(rng.choice(base_addrs))

    # Phase 2: one-time full-table pension-audit scan over a much larger,
    # disjoint address range (records beyond the working set), each
    # touched exactly once, in order.
    scan_start_record = working_set_records + 1000  # keep disjoint from the working set
    for i in range(scan_records):
        addrs.append((scan_start_record + i) * record_size)

    # Phase 3: return to the working set -- this is where LRU's
    # scan-pollution shows up as a hit-rate collapse that must be
    # re-warmed from scratch.
    for _ in range(post_repeats):
        if rng.random() < hot_bias:
            addrs.append(rng.choice(hot_addrs))
        else:
            addrs.append(rng.choice(base_addrs))

    return addrs, len(addrs) - post_repeats  # also return the index where post-scan phase begins


def write_trace(path, addrs, header_comment):
    with open(path, "w") as f:
        f.write(f"# {header_comment}\n")
        for a in addrs:
            f.write(f"{a}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True, help="team-assigned seed")
    ap.add_argument("--label", type=str, default="ssnit", help="output filename prefix")
    ap.add_argument("--out-dir", type=str, default=".", help="output directory")
    ap.add_argument("--working-set-records", type=int, default=64,
                     help="number of records in the hot/warm working set")
    ap.add_argument("--record-size", type=int, default=64,
                     help="bytes per record (should equal the cache block size)")
    ap.add_argument("--recency-repeats", type=int, default=20000,
                     help="number of accesses in the pure recency-heavy trace")
    ap.add_argument("--scan-pre-repeats", type=int, default=8000,
                     help="warm-up accesses before the scan, in the scan-heavy trace")
    ap.add_argument("--scan-records", type=int, default=4000,
                     help="number of unique records swept exactly once during the audit scan")
    ap.add_argument("--scan-post-repeats", type=int, default=8000,
                     help="accesses back on the working set after the scan")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    recency = gen_recency_trace(rng, args.working_set_records, args.record_size,
                                 args.recency_repeats)
    write_trace(f"{args.out_dir}/{args.label}_seed{args.seed}_recency.trace", recency,
                f"SSNIT recency-heavy trace, seed={args.seed}, "
                f"working_set_records={args.working_set_records}")

    scan, post_scan_start_idx = gen_scan_trace(
        rng, args.working_set_records, args.record_size,
        args.scan_pre_repeats, args.scan_records, args.scan_post_repeats)
    write_trace(f"{args.out_dir}/{args.label}_seed{args.seed}_scan.trace", scan,
                f"SSNIT scan-heavy trace, seed={args.seed}, "
                f"working_set_records={args.working_set_records}, "
                f"scan_records={args.scan_records}, "
                f"post_scan_start_index={post_scan_start_idx}")

    print(f"[seed {args.seed}] recency trace: {len(recency)} accesses")
    print(f"[seed {args.seed}] scan trace: {len(scan)} accesses "
          f"(post-scan working-set return begins at access #{post_scan_start_idx})")
    print(f"Working set spans records 0..{args.working_set_records - 1} "
          f"({args.working_set_records * args.record_size} bytes) at {args.record_size} B/record.")


if __name__ == "__main__":
    main()
