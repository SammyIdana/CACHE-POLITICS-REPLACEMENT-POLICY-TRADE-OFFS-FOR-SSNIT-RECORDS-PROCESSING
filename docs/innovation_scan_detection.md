# Innovation Challenge — Design Note (Week 3 Draft)

**Project 7 — Cache Politics — Group 2, Topic 7**
**Status: design only. Implementation targeted for Week 4.**

## Idea

A **scan-detection heuristic** layered on top of plain LRU: detect a
run of accesses that are all first-time misses to never-repeated
addresses (the signature of a full-table sweep, e.g. the SSNIT
pension-audit scan), and while that run is in progress, switch the
eviction target from "true LRU victim" to "the line just inserted by
the scan itself" — i.e. temporarily behave like MRU for scan traffic
only, so the scan cannot evict the protected working set at all.

This is deliberately a *cheaper* alternative to ARC: O(1) extra state
per set (a short counter + one flag) versus ARC's four lists per set,
aimed at recovering most of ARC's scan-resistance without its
bookkeeping cost — a concrete trade-off the report can quantify.

## Detection signal

Maintain, per set, a small counter `consecutive_misses`. Increment on
every miss; reset to 0 on every hit. When `consecutive_misses` exceeds
a threshold `T` (candidate: `T = assoc * 2`, i.e. the set has been
completely turned over twice in a row with zero reuse), declare
"scan mode" for that set until the next hit.

## Modified eviction rule while in scan mode

- Normal LRU: evict the true least-recently-used line.
- Scan mode: evict the line that was itself inserted most recently by
  the scan (effectively MRU-among-scan-insertions) rather than the
  working set's genuinely cold lines — i.e. the incoming scan data
  is allowed to thrash *itself*, not the protected lines that arrived
  before scan mode was declared.

## Planned evaluation (Week 3–4)

- Implement as a fifth policy, `--policy lru-scan-detect`, sharing the
  existing LRU line-array core plus the two extra per-set fields.
- Re-run the Week 3 experiment matrix and the post-scan recovery plot
  with this policy added alongside LRU/FIFO/Random/ARC/OPT.
- Success criterion: post-scan recovery hit rate (first window after
  scan ends) within a small margin of ARC's, at materially lower
  per-set state (2 extra fields vs. ARC's 4 lists).
- Explicitly report where it *fails* relative to ARC (e.g. a workload
  with two interleaved scan-like sub-streams, which a single
  per-set counter cannot distinguish) — the project brief calls for
  identifying where an extension's assumptions break, not just where
  it wins.

## Open questions for Week 4

1. Threshold `T` sensitivity — needs a small sweep, not a single guess.
2. Whether the same heuristic composed with ARC (rather than plain
   LRU) is worth trying, or whether that's redundant with what ARC's
   ghost lists already do.
