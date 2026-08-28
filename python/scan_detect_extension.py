#!/usr/bin/env python3
"""
scan_detect_extension.py
------------------------
CPEN 438 - Project 7: Cache Politics - Group 2, Topic 7
Week 4 Innovation Challenge Implementation

Scan-detection heuristic layered on plain LRU:
  - Detects sequential scan patterns via a per-set consecutive-miss counter
  - Temporarily switches to MRU-biased eviction during detected scans
  - Protects the working set from scan pollution at O(1) extra state per set

This module can be:
  1. Run standalone as a demo (python3 scan_detect_extension.py)
  2. Imported and used as a full trace-driven cache simulator
  3. Run against the project's .trace files for experiment-matrix integration

Usage (standalone demo):
    python3 scan_detect_extension.py

Usage (trace-driven):
    python3 scan_detect_extension.py --trace ../traces/ssnit_seed2_scan.trace \
        --size 1024 --assoc 4 --block 64 --policy lru-scan-detect \
        --hit-time 1 --miss-penalty 100

Usage (full experiment matrix with all policies):
    python3 scan_detect_extension.py --trace ../traces/ssnit_seed2_scan.trace \
        --size 1024 --assoc 4 --block 64 --policy all \
        --hit-time 1 --miss-penalty 100

Usage (threshold sensitivity sweep):
    python3 scan_detect_extension.py --trace ../traces/ssnit_seed2_scan.trace \
        --size 1024 --assoc 4 --block 64 --policy sweep \
        --hit-time 1 --miss-penalty 100
"""

import argparse
import math
import random
import sys
import os
import csv


# =====================================================================
# Cache Line and Set structures
# =====================================================================

class CacheLine:
    """A single cache line with valid bit, tag, and ordering metadata."""
    __slots__ = ('valid', 'tag', 'order_key')

    def __init__(self):
        self.valid = False
        self.tag = 0
        self.order_key = 0


class ScanState:
    """Per-set scan-detection state: only 2 extra fields vs ARC's 4 lists."""
    __slots__ = ('consecutive_misses', 'scan_mode')

    def __init__(self):
        self.consecutive_misses = 0
        self.scan_mode = False


# =====================================================================
# ARC implementation (Megiddo & Modha, FAST '03)
# =====================================================================

class ARCSet:
    """
    Per-set ARC state with T1/T2 (cache-resident) and B1/B2 (ghost) lists.
    Lists are Python lists used as ordered sequences: index 0 = LRU end,
    index -1 = MRU end.
    """

    def __init__(self, cap):
        self.cap = cap       # = associativity
        self.t1 = []         # recency cache list (tags)
        self.t2 = []         # frequency cache list (tags)
        self.b1 = []         # recency ghost list (metadata only)
        self.b2 = []         # frequency ghost list (metadata only)
        self.p = 0           # adaptive target size for T1

    def _replace(self, x_in_b2):
        """REPLACE(x, p) per the paper: evict one line from T1 or T2."""
        if self.t1 and ((x_in_b2 and len(self.t1) == self.p) or
                        (len(self.t1) > self.p)):
            victim = self.t1.pop(0)           # evict LRU of T1
            if len(self.b1) >= self.cap:
                self.b1.pop(0)                # keep ghost bounded
            self.b1.append(victim)            # push to MRU of B1
        else:
            if self.t2:
                victim = self.t2.pop(0)       # evict LRU of T2
                if len(self.b2) >= self.cap:
                    self.b2.pop(0)
                self.b2.append(victim)

    def access(self, tag):
        """Process one access. Returns True on hit, False on miss."""
        # Case I: hit in T1 or T2
        if tag in self.t1:
            self.t1.remove(tag)
            self.t2.append(tag)               # promote to MRU of T2
            return True

        if tag in self.t2:
            self.t2.remove(tag)
            self.t2.append(tag)               # move to MRU of T2
            return True

        # Case II: ghost hit in B1 -> grow p (favour recency)
        if tag in self.b1:
            delta = max(1, len(self.b2) // max(1, len(self.b1)))
            self.p = min(self.p + delta, self.cap)
            self._replace(False)
            self.b1.remove(tag)
            self.t2.append(tag)
            return False                      # data miss, ghost hit

        # Case III: ghost hit in B2 -> shrink p (favour frequency)
        if tag in self.b2:
            delta = max(1, len(self.b1) // max(1, len(self.b2)))
            self.p = max(self.p - delta, 0)
            self._replace(True)
            if tag in self.b2:      # guard: _replace may have evicted it
                self.b2.remove(tag)
            self.t2.append(tag)
            return False

        # Case IV: completely new to this set
        l1 = len(self.t1) + len(self.b1)
        if l1 == self.cap:
            if len(self.t1) < self.cap:
                if self.b1:
                    self.b1.pop(0)
                self._replace(False)
            else:
                self.t1.pop(0)
        elif l1 < self.cap:
            total = len(self.t1) + len(self.t2) + len(self.b1) + len(self.b2)
            if total >= self.cap:
                if total == 2 * self.cap and self.b2:
                    self.b2.pop(0)
                self._replace(False)

        self.t1.append(tag)
        return False


# =====================================================================
# Cache Simulator (supports LRU, FIFO, Random, ARC, LRU-Scan-Detect)
# =====================================================================

class CacheSimulator:
    """
    Trace-driven set-associative cache simulator with pluggable
    replacement policies.
    """

    POLICIES = ('lru', 'fifo', 'random', 'arc', 'lru-scan-detect')

    def __init__(self, cache_size, assoc, block_size, policy,
                 seed=42, hit_time=1.0, miss_penalty=100.0,
                 scan_threshold_factor=0.5):
        self.cache_size = cache_size
        self.assoc = assoc
        self.block_size = block_size
        self.policy = policy
        self.hit_time = hit_time
        self.miss_penalty = miss_penalty

        self.num_sets = cache_size // (assoc * block_size)
        self.block_offset_bits = int(math.log2(block_size))
        self.index_bits = int(math.log2(self.num_sets))

        self.rng = random.Random(seed)

        # Per-set storage
        if policy == 'arc':
            self.arc_sets = [ARCSet(assoc) for _ in range(self.num_sets)]
            self.lines = None
        else:
            self.lines = [[CacheLine() for _ in range(assoc)]
                          for _ in range(self.num_sets)]
            self.arc_sets = None

        # Scan-detection state (only for lru-scan-detect)
        #
        # CORRECTED threshold reasoning (was: factor=2, i.e. T=2*assoc):
        # a set only holds `assoc` lines, so the ORIGINAL working-set
        # contents of a set are already fully evicted after just `assoc`
        # misses in a row -- reaching a threshold >= assoc therefore means
        # scan-mode activates only after there is nothing left to protect.
        # Measured on the real seed-2 scan trace at assoc=4: T=8 (factor=2)
        # gave 0.0000 hit-rate improvement over plain LRU; sweeping smaller
        # thresholds shows the real optimum around T=assoc/2 (here, T=2),
        # which detects the scan while roughly half the set's original
        # lines are still resident and worth protecting. T=1 is too
        # aggressive (false-triggers on ordinary single misses and
        # collapses hit rate); T>=assoc reproduces the original bug.
        self.scan_threshold = max(1, round(scan_threshold_factor * assoc))
        if policy == 'lru-scan-detect':
            self.scan_states = [ScanState() for _ in range(self.num_sets)]
        else:
            self.scan_states = None

        # Counters
        self.clock = 0
        self.accesses = 0
        self.hits = 0
        self.misses = 0

        # Per-access log (for post-scan recovery analysis)
        self.hit_log = []

    def _decompose_address(self, addr):
        """Split byte address into (tag, set_index)."""
        block_addr = addr >> self.block_offset_bits
        set_idx = block_addr & (self.num_sets - 1)
        tag = block_addr >> self.index_bits
        return tag, set_idx

    def _access_lru(self, tag, set_idx):
        """Standard LRU: update order_key on every hit."""
        s = self.lines[set_idx]
        self.clock += 1

        # Search for hit
        for line in s:
            if line.valid and line.tag == tag:
                line.order_key = self.clock
                return True

        # Miss: find victim
        empty = next((l for l in s if not l.valid), None)
        if empty is not None:
            victim = empty
        else:
            victim = min(s, key=lambda l: l.order_key)

        victim.valid = True
        victim.tag = tag
        victim.order_key = self.clock
        return False

    def _access_fifo(self, tag, set_idx):
        """FIFO: order_key set on insert, never updated on hit."""
        s = self.lines[set_idx]
        self.clock += 1

        for line in s:
            if line.valid and line.tag == tag:
                return True  # hit — do NOT update order_key

        empty = next((l for l in s if not l.valid), None)
        if empty is not None:
            victim = empty
        else:
            victim = min(s, key=lambda l: l.order_key)

        victim.valid = True
        victim.tag = tag
        victim.order_key = self.clock
        return False

    def _access_random(self, tag, set_idx):
        """Random: uniformly random victim selection."""
        s = self.lines[set_idx]
        self.clock += 1

        for line in s:
            if line.valid and line.tag == tag:
                line.order_key = self.clock
                return True

        empty = next((l for l in s if not l.valid), None)
        if empty is not None:
            victim = empty
        else:
            victim = self.rng.choice(s)

        victim.valid = True
        victim.tag = tag
        victim.order_key = self.clock
        return False

    def _access_arc(self, tag, set_idx):
        """ARC: delegate to the per-set ARCSet object."""
        return self.arc_sets[set_idx].access(tag)

    def _access_scan_detect(self, tag, set_idx):
        """
        LRU with scan-detection heuristic (innovation challenge).

        Core idea:
          - Track consecutive misses per set
          - When consecutive_misses >= threshold, enter scan mode
          - In scan mode: evict MRU (most recently inserted) instead of LRU
          - On any hit: exit scan mode, reset counter

        Effect: scan data thrashes itself (MRU eviction) instead of
        evicting the protected working set (which sits at the LRU end).

        Threshold must be set BELOW assoc (see scan_threshold comment in
        __init__) -- otherwise the set's original contents are already
        fully evicted by the time detection fires, and this degenerates
        to plain LRU with extra bookkeeping and no benefit.
        """
        s = self.lines[set_idx]
        ss = self.scan_states[set_idx]
        self.clock += 1

        # --- Check for hit ---
        for line in s:
            if line.valid and line.tag == tag:
                line.order_key = self.clock
                # Hit: reset scan detection — scan is over
                ss.consecutive_misses = 0
                ss.scan_mode = False
                return True

        # --- Miss: update scan-detection state ---
        ss.consecutive_misses += 1
        if ss.consecutive_misses >= self.scan_threshold:
            ss.scan_mode = True

        # --- Select victim ---
        empty = next((l for l in s if not l.valid), None)
        if empty is not None:
            victim = empty
        elif ss.scan_mode:
            # SCAN MODE: evict MRU (highest order_key)
            # The most recently inserted line is likely scan data —
            # evict it so the scan thrashes itself, not the working set
            victim = max(s, key=lambda l: l.order_key)
        else:
            # NORMAL LRU: evict the least recently used line
            victim = min(s, key=lambda l: l.order_key)

        victim.valid = True
        victim.tag = tag
        victim.order_key = self.clock
        return False

    def access(self, addr):
        """Process a single memory access. Returns True if hit."""
        tag, set_idx = self._decompose_address(addr)
        self.accesses += 1

        dispatch = {
            'lru':             self._access_lru,
            'fifo':            self._access_fifo,
            'random':          self._access_random,
            'arc':             self._access_arc,
            'lru-scan-detect': self._access_scan_detect,
        }

        hit = dispatch[self.policy](tag, set_idx)

        if hit:
            self.hits += 1
        else:
            self.misses += 1

        self.hit_log.append(1 if hit else 0)
        return hit

    def run_trace(self, trace_path):
        """Run the simulator on a trace file (one decimal address per line)."""
        with open(trace_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                addr = int(line)
                self.access(addr)

    @property
    def hit_rate(self):
        return self.hits / self.accesses if self.accesses else 0.0

    @property
    def miss_rate(self):
        return 1.0 - self.hit_rate

    @property
    def amat(self):
        return self.hit_time + self.miss_rate * self.miss_penalty

    def summary(self):
        """Return a dict summarising the simulation results."""
        return {
            'policy':     self.policy,
            'cache_size': self.cache_size,
            'assoc':      self.assoc,
            'block_size': self.block_size,
            'num_sets':   self.num_sets,
            'accesses':   self.accesses,
            'hits':       self.hits,
            'misses':     self.misses,
            'hit_rate':   round(self.hit_rate, 6),
            'miss_rate':  round(self.miss_rate, 6),
            'amat':       round(self.amat, 4),
        }

    def windowed_hit_rate(self, window=200):
        """
        Compute hit rate over sliding windows of `window` accesses.
        Used for the post-scan recovery analysis.
        """
        rates = []
        for i in range(0, len(self.hit_log), window):
            chunk = self.hit_log[i:i + window]
            if chunk:
                rates.append(sum(chunk) / len(chunk))
        return rates


# =====================================================================
# Post-scan recovery comparison
# =====================================================================

def run_post_scan_recovery(trace_path, size, assoc, block, hit_time,
                           miss_penalty, seed, window=200):
    """
    Run all policies on the same trace and produce windowed hit-rate
    data for each, suitable for the post-scan recovery plot.
    """
    policies = ['lru', 'fifo', 'random', 'arc', 'lru-scan-detect']
    results = {}

    for pol in policies:
        sim = CacheSimulator(size, assoc, block, pol,
                             seed=seed, hit_time=hit_time,
                             miss_penalty=miss_penalty)
        sim.run_trace(trace_path)
        results[pol] = {
            'summary':  sim.summary(),
            'windowed': sim.windowed_hit_rate(window),
        }
        print(f"  {pol:20s}  hit_rate={sim.hit_rate:.4f}  amat={sim.amat:.2f}")

    return results


# =====================================================================
# Threshold sensitivity sweep
# =====================================================================

def threshold_sweep(trace_path, size, assoc, block, hit_time,
                    miss_penalty, seed):
    """
    Sweep the scan-detection threshold to find the optimal value.

    Tests factors BELOW assoc as well as at/above it. This range was
    widened after measurement showed factor>=1 (T>=assoc) always
    activates scan-mode only after a set's original contents are
    already fully evicted, making the heuristic indistinguishable from
    plain LRU (see the CORRECTED threshold note in CacheSimulator).
    """
    print("\n=== Threshold Sensitivity Sweep ===")
    print(f"{'Threshold':>12s}  {'Factor':>8s}  {'Hit Rate':>10s}  {'AMAT':>10s}")
    print("-" * 50)

    best_hr = 0
    best_t = 0

    for factor in [0.25, 0.4, 0.5, 0.6, 0.75, 1, 1.5, 2, 3, 4]:
        threshold = max(1, round(factor * assoc))
        sim = CacheSimulator(size, assoc, block, 'lru-scan-detect',
                             seed=seed, hit_time=hit_time,
                             miss_penalty=miss_penalty,
                             scan_threshold_factor=factor)
        sim.run_trace(trace_path)
        print(f"{threshold:>12d}  {factor:>8.2f}  {sim.hit_rate:>10.4f}  {sim.amat:>10.2f}")

        if sim.hit_rate > best_hr:
            best_hr = sim.hit_rate
            best_t = threshold

    print(f"\nBest threshold: T={best_t} (hit_rate={best_hr:.4f})")
    return best_t


# =====================================================================
# Standalone demo: hand-crafted trace showing scan detection in action
# =====================================================================

def run_demo():
    """
    Demonstrate the scan-detection heuristic on a hand-crafted trace
    and compare against plain LRU to show the protection effect.
    """
    print("=" * 70)
    print("SCAN-DETECTION HEURISTIC — STANDALONE DEMO")
    print("Cache: 256 B, 4-way, 64 B blocks → 1 set (all addresses map here)")
    print("Threshold: T = assoc/2 = 2 consecutive misses (corrected; see")
    print("CacheSimulator's scan_threshold comment for why T=2*assoc failed)")
    print("=" * 70)

    # With 256B cache, 4-way, 64B blocks → 1 set
    # All addresses in range 0..255 map to the same (only) set
    SIZE, ASSOC, BLOCK = 256, 4, 64

    # Phase 1: Establish a working set of 4 blocks (addresses 0, 64, 128, 192)
    working_set = [0, 64, 128, 192]

    # Phase 2: Repeat the working set several times to establish recency
    ws_repeat = working_set * 5   # 20 accesses

    # Phase 3: Scan — 20 unique addresses from a different region
    # Each maps to the same single set but with different tags
    scan = [256 + i * 64 for i in range(20)]

    # Phase 4: Access working set again — how many survive?
    post_scan = working_set

    full_trace = working_set + ws_repeat + scan + post_scan

    # --- Run with plain LRU ---
    print("\n--- Plain LRU ---")
    sim_lru = CacheSimulator(SIZE, ASSOC, BLOCK, 'lru', seed=42)
    for i, addr in enumerate(full_trace):
        phase = ("WS-init" if i < 4 else
                 "WS-repeat" if i < 24 else
                 "SCAN" if i < 44 else
                 "POST-SCAN")
        hit = sim_lru.access(addr)
        tag = addr >> int(math.log2(BLOCK))
        if phase in ("SCAN", "POST-SCAN"):
            print(f"  [{phase:>9s}] addr={addr:>5d} tag={tag:>3d} "
                  f"-> {'HIT' if hit else 'MISS'}")

    ws_hits_lru = sum(sim_lru.hit_log[-4:])
    print(f"\n  LRU post-scan working-set hits: {ws_hits_lru}/4")

    # --- Run with scan-detect ---
    print("\n--- LRU with Scan Detection ---")
    sim_sd = CacheSimulator(SIZE, ASSOC, BLOCK, 'lru-scan-detect', seed=42)
    for i, addr in enumerate(full_trace):
        phase = ("WS-init" if i < 4 else
                 "WS-repeat" if i < 24 else
                 "SCAN" if i < 44 else
                 "POST-SCAN")
        hit = sim_sd.access(addr)
        tag = addr >> int(math.log2(BLOCK))
        ss = sim_sd.scan_states[0]
        if phase in ("SCAN", "POST-SCAN"):
            mode = "MRU" if ss.scan_mode else "LRU"
            print(f"  [{phase:>9s}] addr={addr:>5d} tag={tag:>3d} "
                  f"-> {'HIT' if hit else 'MISS'}  "
                  f"consec={ss.consecutive_misses:>2d}  "
                  f"scan_mode={ss.scan_mode}  eviction={mode}")

    ws_hits_sd = sum(sim_sd.hit_log[-4:])
    print(f"\n  Scan-detect post-scan working-set hits: {ws_hits_sd}/4")

    # --- Run with ARC for comparison ---
    sim_arc = CacheSimulator(SIZE, ASSOC, BLOCK, 'arc', seed=42)
    for addr in full_trace:
        sim_arc.access(addr)
    ws_hits_arc = sum(sim_arc.hit_log[-4:])

    # --- Summary ---
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Policy':<25s} {'Total Hit Rate':>15s} {'Post-Scan WS Hits':>20s}")
    print("-" * 60)
    print(f"{'LRU':<25s} {sim_lru.hit_rate:>15.4f} {ws_hits_lru:>17d}/4")
    print(f"{'LRU-Scan-Detect':<25s} {sim_sd.hit_rate:>15.4f} {ws_hits_sd:>17d}/4")
    print(f"{'ARC':<25s} {sim_arc.hit_rate:>15.4f} {ws_hits_arc:>17d}/4")

    print("\n--- Architectural Insight ---")
    print("The scan-detection heuristic protects the working set by")
    print("switching to MRU eviction once a scan is detected (after T")
    print("consecutive misses). Scan data then thrashes itself instead")
    print("of evicting the protected working-set lines at the LRU end.")
    print("")
    print("Trade-off vs ARC:")
    print(f"  Extra state per set:  scan-detect = 2 fields,  ARC = 4 lists")
    print(f"  Generality:           scan-detect = single long scans only")
    print(f"                        ARC = adapts to any mixed pattern")


# =====================================================================
# CLI entry point
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Cache simulator with scan-detection heuristic "
                    "(Project 7 Innovation Challenge)")
    parser.add_argument('--trace', help='Path to trace file')
    parser.add_argument('--size', type=int, default=1024,
                        help='Cache size in bytes (default: 1024)')
    parser.add_argument('--assoc', type=int, default=4,
                        help='Associativity (default: 4)')
    parser.add_argument('--block', type=int, default=64,
                        help='Block size in bytes (default: 64)')
    parser.add_argument('--policy', default='demo',
                        choices=['lru', 'fifo', 'random', 'arc',
                                 'lru-scan-detect', 'all', 'sweep', 'demo'],
                        help='Policy to run (default: demo)')
    parser.add_argument('--seed', type=int, default=2,
                        help='Random seed (default: 2, team assignment)')
    parser.add_argument('--hit-time', type=float, default=1.0,
                        help='Hit time in cycles (default: 1.0)')
    parser.add_argument('--miss-penalty', type=float, default=100.0,
                        help='Miss penalty in cycles (default: 100.0)')
    parser.add_argument('--out', help='Output CSV path for results')
    parser.add_argument('--window', type=int, default=200,
                        help='Window size for recovery analysis (default: 200)')

    args = parser.parse_args()

    # --- Demo mode (no trace file needed) ---
    if args.policy == 'demo' or not args.trace:
        run_demo()
        return

    # --- Validate trace file ---
    if not os.path.isfile(args.trace):
        print(f"Error: trace file '{args.trace}' not found.", file=sys.stderr)
        sys.exit(1)

    # --- Threshold sweep ---
    if args.policy == 'sweep':
        threshold_sweep(args.trace, args.size, args.assoc, args.block,
                        args.hit_time, args.miss_penalty, args.seed)
        return

    # --- All policies comparison ---
    if args.policy == 'all':
        print(f"Running all policies on: {args.trace}")
        print(f"Cache: {args.size}B, {args.assoc}-way, {args.block}B blocks\n")
        results = run_post_scan_recovery(
            args.trace, args.size, args.assoc, args.block,
            args.hit_time, args.miss_penalty, args.seed, args.window)

        if args.out:
            with open(args.out, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'policy', 'cache_size', 'assoc', 'block_size',
                    'num_sets', 'accesses', 'hits', 'misses',
                    'hit_rate', 'miss_rate', 'amat'])
                writer.writeheader()
                for pol, data in results.items():
                    writer.writerow(data['summary'])
            print(f"\nResults written to {args.out}")
        return

    # --- Single policy run ---
    sim = CacheSimulator(args.size, args.assoc, args.block, args.policy,
                         seed=args.seed, hit_time=args.hit_time,
                         miss_penalty=args.miss_penalty)
    sim.run_trace(args.trace)
    s = sim.summary()

    print(f"policy={s['policy']} size={s['cache_size']} assoc={s['assoc']} "
          f"block={s['block_size']} sets={s['num_sets']} "
          f"accesses={s['accesses']} hits={s['hits']} misses={s['misses']} "
          f"hit_rate={s['hit_rate']:.6f} amat={s['amat']:.4f}")

    if args.out:
        need_header = not os.path.isfile(args.out)
        with open(args.out, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'policy', 'cache_size', 'assoc', 'block_size',
                'num_sets', 'accesses', 'hits', 'misses',
                'hit_rate', 'miss_rate', 'amat'])
            if need_header:
                writer.writeheader()
            writer.writerow(s)
        print(f"Result appended to {args.out}")


if __name__ == '__main__':
    main()
