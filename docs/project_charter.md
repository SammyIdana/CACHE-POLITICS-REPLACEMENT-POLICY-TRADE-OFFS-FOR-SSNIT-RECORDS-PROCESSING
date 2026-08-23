# Project Charter — Week 1 Deliverable

**Project:** 7 — Cache Politics: Replacement Policy Trade-offs for SSNIT Records Processing
**Team:** Group 2
**Assigned seed:** 2

## Team members & roles
*(fill in names — role structure per Part I §9 of the course portfolio)*

| Role | Name |
|---|---|
| Project Manager & Systems Integrator | _TBD_ |
| Computer Architecture & Hardware Design Lead | _TBD_ |
| C/C++ Implementation & Performance Lead | _TBD_ |
| Python/MATLAB Experimentation & Data Analysis Lead | _TBD_ |
| Testing, Validation, Documentation & Reproducibility Lead | _TBD_ |

## Chosen papers for review
1. Megiddo, N. and Modha, D.S. "ARC: A Self-Tuning, Low Overhead Replacement Cache." *FAST '03.*
2. Jouppi, N.P. "Improving Direct-Mapped Cache Performance by the Addition of a Small Fully-Associative Cache and Prefetch Buffers." *ISCA '90.*

## Problem statement (team restatement)
No single cache replacement policy dominates across access patterns.
LRU performs well under strong recency locality but degrades sharply
when a one-time full scan (e.g. a pension-audit sweep of SSNIT member
records) evicts the working set it was protecting. ARC is designed to
adapt automatically between recency and frequency signals without
manual tuning. This project builds a configurable set-associative cache
simulator implementing LRU, FIFO, Random, and ARC, and measures hit
rate and AMAT for each on both a steady-state recency-heavy trace and a
scan-heavy trace derived from a shared SSNIT-records access model, to
empirically demonstrate the trade-off rather than assume it.

## Hardware/software configuration
- Simulator: C99, compiled with `gcc -O2`
- Trace generation & analysis: Python 3 (`random`, `matplotlib`, `numpy`)
- Analytical model & validation: MATLAB
- Version control: Git (tagged weekly releases per course integrity framework)

## Planned innovation-challenge idea (subject to revision by Week 3)
A scan-detection heuristic that temporarily switches LRU into an
MRU-biased eviction mode when a long run of unique, never-repeated
addresses is detected, evaluated against plain ARC on the same
scan-heavy trace.

## Anticipated risk / blocker
Correctly implementing ARC's ghost-list (B1/B2) bookkeeping as metadata
only (no cached data) is the most error-prone part of the
implementation; mitigated by the automated hand-trace validation gate
(`tests/test_hand_trace.py`) before any full-trace result is trusted.

## Repository URL
_TBD — add the team's Git remote here once created._
