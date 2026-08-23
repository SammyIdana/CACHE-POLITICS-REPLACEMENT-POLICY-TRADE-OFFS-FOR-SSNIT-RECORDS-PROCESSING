# Requirements Specification — Week 1 Deliverable

**Project 7 — Cache Politics — Group 2, Topic 7**

## 1. Functional requirements
- FR1: The cache core must correctly implement set-associative addressing
  (tag/index/block-offset decomposition) for configurable cache size,
  associativity, and block size.
- FR2: The simulator must implement four pluggable replacement policies —
  LRU, FIFO, Random, and ARC — sharing the identical cache core.
- FR3: All four policies must be evaluated on the identical trace and
  cache geometry for any single experiment.
- FR4: ARC's ghost lists (B1, B2) must track tags only, never cached
  data, and must be accounted for separately from resident lines (T1,
  T2) in any memory-overhead discussion.

## 2. Non-functional requirements
- NFR1: The simulator must process at least 500,000 trace accesses in
  under 30 seconds on a standard lab machine.
- NFR2: Cache geometry (size, associativity, block size) must be
  configurable via command-line arguments, not recompiled per
  experiment.

## 3. Input requirements
- A trace file: one decimal byte address per line (`#`-prefixed lines
  ignored as comments).
- Two trace variants per team, generated from the team's unique seed:
  a recency-heavy trace and a scan-heavy trace (`gen_ssnit_trace.py`).

## 4. Output requirements
- Per-run summary: policy, cache geometry, accesses, hits, misses, hit
  rate, AMAT.
- A machine-readable CSV row per run, suitable for downstream analysis
  (`--out` flag).

## 5. Testing requirements
- Each policy's eviction decision must be verified against a
  hand-traced 10-access mini-sequence (see
  `docs/hand_trace_derivation.md`, automated by
  `tests/test_hand_trace.py`) before any full-trace result is trusted.

## 6. Reproducibility requirements
- Trace seed, cache geometry, and latency parameters (hit time, miss
  penalty) must be recorded for every run that appears in the report
  (the CSV output format satisfies this).

## 7. Experimental design (summary — full table in the final report)
- Independent variables: replacement policy (4), trace type (2, +OPT
  extension in Week 3/4), cache size (3 required sizes).
- Dependent variables: hit rate, AMAT.
- Required plots: hit-rate bar chart, AMAT bar chart, hit-rate vs.
  cache-size line chart (scan-heavy trace), post-scan recovery curve
  (added Week 3).

## 8. Architecture diagram

```
                     +---------------------------+
   trace file  ----> |   cache_sim (C, src/)      |
 (decimal addrs)     |                             |
                     |  1. address decomposition   |
                     |     (tag / index / offset)  |
                     |  2. per-set line/ARC state   |
                     |  3. policy dispatch:         |
                     |     LRU | FIFO | RANDOM | ARC|
                     |  4. hit/miss + AMAT accounting|
                     +---------------------------+
                                  |
                                  v
                     results/experiment_matrix.csv
                                  |
                 +----------------+----------------+
                 v                                 v
   python/analyze_cache_results.py     matlab/amat_hitrate_model.m
   (tables + hit-rate/AMAT plots)      (analytical AMAT sensitivity
                                         model, validated against
                                         measured data)

   python/gen_ssnit_trace.py  --seed 2  -->  traces/*.trace
   (feeds cache_sim above; independent of the analysis path)
```
