# AI-Use Declaration

**Project 7 — Cache Politics — Group 2, Topic 7**

Per Part I §7 of the course portfolio, every instance of AI assistance
is disclosed here. Fill in one row per instance; do not leave prior
weeks' rows out when adding new ones.

| AI tool | Date | Prompt/query (summary) | Output received (summary) | How verified | What was modified | Final section(s) containing AI-assisted material |
|---|---|---|---|---|---|---|
| _e.g. Claude_ | _YYYY-MM-DD_ | _e.g. "scaffold a set-associative cache simulator supporting LRU/FIFO/RANDOM/ARC"_ | _e.g. initial cache_sim.c, trace generator, analysis scripts, hand-trace test_ | _Compiled and run; hand-traced 10-access sequence derived independently and checked against simulator output (all three policies pass); results spot-checked against expected qualitative trends (ARC ≥ LRU on scan-heavy trace)_ | _Cache-size/associativity used for the hand-trace test reduced to 128B/2-way to keep the derivation tractable by hand; ARC ghost-list bookkeeping reviewed line-by-line against the Megiddo & Modha paper's REPLACE(x,p) pseudocode_ | _src/cache_sim.c, python/gen_ssnit_trace.py, python/analyze_cache_results.py, matlab/amat_hitrate_model.m, tests/test_hand_trace.py_ |

**Permitted uses:** clarifying a concept, explaining an error message,
suggesting test cases, improving documentation or grammar, and — as
used here — scaffolding an initial implementation that the team then
reviews, tests, and is individually able to explain and modify live.

**Restricted/prohibited uses:** submitting the code without
understanding it, fabricating results or citations, or treating this
declaration as satisfied without every team member being able to
explain and live-modify any part of the codebase, per the individual
verification requirement in Part I §7.

**Team note:** every member must be able to trace an ARC ghost-list hit
and a forwarding/eviction decision live, unaided, before the Week 4
defence — this is the individual-verification standard the
declaration exists to support, not a substitute for it.
