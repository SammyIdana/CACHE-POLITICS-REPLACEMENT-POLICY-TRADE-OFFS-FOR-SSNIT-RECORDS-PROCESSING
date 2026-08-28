# Hand-Traced Validation Sequence — Derivation

**CPEN 315/733 — Project 7: Cache Politics — Group 2, Topic 7**

Per the project's testing requirement ("each policy's eviction choice
must be verified against a hand-traced 10-access mini-sequence before
running the full trace"), this document derives, by hand, the expected
hit/miss outcome of a short access sequence under LRU, FIFO, and ARC, for
a 1-set, 2-way associative cache (`--size 128 --assoc 2 --block 64`).

## Sequence

Access order: **A, B, A, C, B, D**
Byte addresses (block size 64B): A=0, B=64, C=128, D=192

## LRU

| Step | Access | Cache before | Result | Cache after (MRU→LRU shown) |
|---|---|---|---|---|
| 1 | A | {} | miss | [A] |
| 2 | B | [A] | miss | [B,A] |
| 3 | A | [B,A] | **hit** | [A,B] |
| 4 | C | [A,B] | miss (evict B, the LRU line) | [C,A] |
| 5 | B | [C,A] | miss (B was evicted at step 4) | [B,C] |
| 6 | D | [B,C] | miss (evict C, the LRU line) | [D,B] |

**LRU total: hits = 1, misses = 5**

## FIFO

FIFO evicts by insertion order only; a hit never changes a line's
position in the eviction queue.

| Step | Access | Queue before (oldest→newest) | Result | Queue after |
|---|---|---|---|---|
| 1 | A | {} | miss | [A] |
| 2 | B | [A] | miss | [A,B] |
| 3 | A | [A,B] | **hit** (queue unchanged) | [A,B] |
| 4 | C | [A,B] | miss (evict A, oldest) | [B,C] |
| 5 | B | [B,C] | **hit** (B was never evicted) | [B,C] |
| 6 | D | [B,C] | miss (evict B, oldest) | [C,D] |

**FIFO total: hits = 2, misses = 4**

This is the specific case the project brief calls out: FIFO's queue
position is insertion-order only, so a hit on B at step 5 is possible
precisely because FIFO's step-4 eviction target (A) differs from LRU's
(B) — a common point of confusion the report is required to address.

## ARC

Cache capacity per set, `c = 2`. Initial state: T1=[], T2=[], B1=[],
B2=[], p=0. (T1/T2 hold resident data; B1/B2 are ghost tag lists —
metadata only, no cached data.)

| Step | Access | Case | Action | p after |
|---|---|---|---|---|
| 1 | A | IV (new) | insert A → T1=[A] | 0 |
| 2 | B | IV (new) | insert B → T1=[A,B] | 0 |
| 3 | A | I (hit, in T1) | move A: T1=[B], T2=[A] | 0 |
| 4 | C | IV (new); T1+B1 not yet full but total=cap → REPLACE | evict LRU of T1 (B) → B1=[B]; insert C → T1=[C] | 0 |
| 5 | B | II (ghost hit in B1) | p←min(2,0+1)=1; REPLACE evicts LRU of T2 (A) → B2=[A]; move B from B1 → T2=[B] | 1 |
| 6 | D | IV (new); REPLACE | T1=[C] has n1=1=p, so evict LRU of T2 (B) → B2=[A,B]; insert D → T1=[C,D] | 1 |

Step 5 is a **ghost hit**: the tag is recognised as recently evicted
and adapts `p` toward recency, but the data itself must still be
re-fetched — it is *not* a cache hit for AMAT purposes. Our simulator
scores case II/III events as misses accordingly (see `arc_access()` in
`src/cache_sim.c`).

**ARC total: hits = 1 (step 3 only), misses = 5**

## Cross-check

Run `tests/test_hand_trace.py`, which encodes exactly this sequence and
asserts the simulator's reported `hits`/`misses` for LRU, FIFO, and ARC
against the table above. All three pass (see `tests/` for the script and
its output).

## Examples

Run the automated hand-trace validator (recommended):

```bash
cd tests
python3 test_hand_trace.py ../src/cache_sim
```

Expected test output (example):

```
[PASS] LRU    hits=1 (expected 1), misses=5 (expected 5)
[PASS] FIFO   hits=2 (expected 2), misses=4 (expected 4)
[PASS] ARC    hits=1 (expected 1), misses=5 (expected 5)

All policies match the hand-traced validation sequence.
```

Run the simulator manually for a single policy using a small trace file:

1. Create a trace file `handtrace_10access.trace` containing the six block addresses (one per line):

```
0
64
0
128
64
192
```

2. Build and run the simulator (from repository root):

```bash
cd src
gcc -O2 -Wall -o cache_sim cache_sim.c -lm
./cache_sim --policy lru --size 128 --assoc 2 --block 64 --trace ../tests/handtrace_10access.trace
```

The simulator prints a single summary line that includes `hits=` and `misses=` which the test harness parses.

Notes:

- The automated test uses `../src/cache_sim` by default; pass a different binary path as the first argument to `test_hand_trace.py` if needed.
- The trace file format is one decimal byte address per line; lines starting with `#` are ignored.

