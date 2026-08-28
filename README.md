# Cache Politics: Replacement Policy Trade-offs for SSNIT Records Processing

**CPEN 438 — Advanced Computer Architecture Systems and Design**
**Group 2 — Topic 7**

## Purpose

Trace-driven set-associative cache simulator comparing four replacement
policies — LRU, FIFO, Random, and Megiddo & Modha's ARC (Adaptive
Replacement Cache) — on a synthetic SSNIT-records-processing workload,
to quantitatively reproduce ARC's central claim: near-LRU performance on
recency-heavy access patterns, and substantially better performance than
LRU on scan-heavy patterns.

## Repository structure

```
proj7/
├── src/
│   └── cache_sim.c            # the simulator (LRU/FIFO/RANDOM/ARC)
├── python/
│   ├── gen_ssnit_trace.py     # seeded trace generator (recency + scan)
│   └── analyze_cache_results.py  # experiment runner, tables, plots
├── matlab/
│   └── amat_hitrate_model.m   # analytical AMAT model + validation
├── tests/
│   └── test_hand_trace.py     # automated hand-trace validation (W2 gate)
├── docs/
│   └── hand_trace_derivation.md  # by-hand derivation backing the test
├── traces/                    # generated trace files (seed-specific)
└── results/                   # experiment_matrix.csv + plots
```

## Requirements

- `gcc` (or any C99 compiler) and `libm`
- Python 3.8+, with `matplotlib`/`numpy` for plots (`pip install matplotlib numpy --break-system-packages`)
- MATLAB (or Octave) for `amat_hitrate_model.m`

## Build

```bash
cd src
gcc -O2 -Wall -o cache_sim cache_sim.c -lm
```

## Generate this team's traces (seed 2)

```bash
cd python
python3 gen_ssnit_trace.py --seed 2 --label ssnit --out-dir ../traces \
    --working-set-records 64 --record-size 64 \
    --recency-repeats 20000 --scan-pre-repeats 8000 \
    --scan-records 4000 --scan-post-repeats 8000
```

## Run a single configuration

```bash
./src/cache_sim --policy arc --size 1024 --assoc 4 --block 64 \
    --trace traces/ssnit_seed2_scan.trace --seed 2 \
    --hit-time 1 --miss-penalty 100 --label demo --out results/summary.csv
```

## Run the full experiment matrix (policy × trace type × cache size)

```bash
cd python
python3 analyze_cache_results.py --sim ../src/cache_sim \
    --trace-dir ../traces --seed 2 --label ssnit --out-dir ../results \
    --sizes 512 1024 2048
```

This writes `results/experiment_matrix.csv` and three plots: hit-rate by
policy/trace type, AMAT by policy/trace type, and hit-rate vs. cache
size for the scan-heavy trace.

## Validate before trusting results (hand-trace gate)

```bash
cd tests
python3 test_hand_trace.py ../src/cache_sim
```

Must print `PASS` for LRU, FIFO, and ARC before the full-trace results
above are trusted, per the project's testing requirement. See
`docs/hand_trace_derivation.md` for the by-hand working this test
encodes.

## Run the post-scan recovery analysis (Week 3)

```bash
cd python
python3 post_scan_recovery.py --sim ../src/cache_sim \
    --trace ../traces/ssnit_seed2_scan.trace \
    --size 1024 --assoc 4 --block 64 --out-dir ../results --window 200
```

Writes `results/post_scan_recovery.csv` and `results/post_scan_recovery.png`,
showing windowed hit rate for every policy (including OPT) starting from
the moment the audit scan ends. This is the plot that makes ARC's
faster-than-LRU recovery visible directly, rather than only as a
single aggregate hit-rate number.

## Cross-check the analytical model

In MATLAB, from `matlab/`:
```matlab
amat_hitrate_model
```
(requires `results/experiment_matrix.csv` to already exist — regenerate
it with `analyze_cache_results.py` first if you've re-run experiments.)
Expect console output ending in `PASS: analytical model matches
simulator output within 0.05 cycles.` plus a saved
`results/amat_sensitivity_model.png`. (A Python-only cross-check of the
same formula against the current `experiment_matrix.csv` — for use if
MATLAB/Octave isn't installed on your machine — confirms a residual of
~1e-15 cycles, i.e. floating-point noise; see Week 3 report §4.)

## Reproducing this team's seed

Team 2's assigned seed is **2** (see `docs/project_charter.md`). All
generator invocations above assume `--seed 2`; re-running with the same
seed reproduces byte-identical traces.

## Status (as of Week 3 submission)

- [x] Cache core: set-associative addressing, configurable size/assoc/block
- [x] LRU replacement policy
- [x] FIFO replacement policy
- [x] Random replacement policy
- [x] ARC replacement policy (T1/T2/B1/B2, adaptive `p`)
- [x] Hand-traced validation (LRU/FIFO/ARC) — automated, passing
- [x] Trace generator (recency-heavy + scan-heavy, seeded)
- [x] Experiment-matrix runner + plots
- [x] MATLAB analytical AMAT model + validation cross-check
- [x] OPT (Belady) comparison — implemented Week 3, confirmed upper bound in all 30 experiment-matrix rows
- [x] Post-scan hit-rate recovery plot — Week 3
- [x] MATLAB AMAT model — Python cross-check passing; MATLAB run pending on team hardware
- [ ] Innovation challenge (scan-detection heuristic) — designed Week 3 (docs/innovation_scan_detection.md), implementation targeted for Week 4
- [ ] Victim-cache extension — Advanced-level extension, optional for Week 4
