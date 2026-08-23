#!/usr/bin/env python3
"""
test_hand_trace.py
-------------------
CPEN 315/733 - Project 7: Cache Politics - Group 2, Topic 7

Automated version of the hand-traced 10-access validation sequence
required before the full SSNIT trace is trusted (see Part I S5 /
Project 7 S G "Testing" requirement).

Sequence (1 set, 2-way associative, 64B blocks -> 128B cache):
    Access order:  A  B  A  C  B  D
    Addresses:     0 64  0 128 64 192

Hand-derived expectations (see docs/hand_trace_derivation.md for the
full cycle-by-cycle working):
    LRU:    hits=1, misses=5  (A B A C B D -> only the 3rd access, A, hits)
    FIFO:   hits=2, misses=4  (A survives the 4th access as B; B then hits at access 5)
    ARC:    hits=1, misses=5  (behaves like LRU on this short a warm-up window)

Run: python3 test_hand_trace.py [path-to-cache_sim-binary]
Exits 0 if every policy matches, 1 otherwise.
"""
import subprocess
import sys
import re
import os

TRACE_CONTENT = """# hand-traced validation sequence: A B A C B D
0
64
0
128
64
192
"""

EXPECTED = {
    "lru":  {"hits": 1, "misses": 5},
    "fifo": {"hits": 2, "misses": 4},
    "arc":  {"hits": 1, "misses": 5},
}


def run_case(binary, policy, trace_path):
    result = subprocess.run(
        [binary, "--policy", policy, "--size", "128", "--assoc", "2",
         "--block", "64", "--trace", trace_path],
        capture_output=True, text=True, check=True)
    out = result.stdout
    hits = int(re.search(r"hits=(\d+)", out).group(1))
    misses = int(re.search(r"misses=(\d+)", out).group(1))
    return hits, misses


def main():
    binary = sys.argv[1] if len(sys.argv) > 1 else "../src/cache_sim"
    trace_path = "handtrace_10access.trace"
    with open(trace_path, "w") as f:
        f.write(TRACE_CONTENT)

    all_pass = True
    for policy, expected in EXPECTED.items():
        hits, misses = run_case(binary, policy, trace_path)
        ok = (hits == expected["hits"] and misses == expected["misses"])
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {policy.upper():6s} hits={hits} (expected {expected['hits']}), "
              f"misses={misses} (expected {expected['misses']})")
        all_pass = all_pass and ok

    os.remove(trace_path)
    if not all_pass:
        print("\nOne or more policies diverged from the hand-traced expectation.")
        sys.exit(1)
    print("\nAll policies match the hand-traced validation sequence.")
    sys.exit(0)


if __name__ == "__main__":
    main()
