# Performance Proposal Amendments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing performance proposals explicitly require measurable Python runtime experiments and an evidence-gated Python-versus-Rust decision.

**Architecture:** Amend the three existing proposals without selecting an implementation prematurely. The compiled-runtime proposal owns Python hypotheses and measurement, the optional-native proposal owns the Rust comparison and adoption decision, and the leadership proposal owns cross-strategy diagnostic evidence.

**Tech Stack:** Markdown proposals, the existing benchmark evidence system, MkDocs, Ruff, Basedpyright, Mypy, and Pytest.

---

### Task 1: Make the Python selection experiment explicit

**Files:**
- Modify: `specs/proposals/2026-09-02-compiled-resolution-runtime-proposal.md`

- [x] Add dense private provider IDs and array/tuple-backed execution tables as a measured representation hypothesis, not a selected architecture.
- [x] Require prototypes to measure the current interpreter, each optimized Python strategy, direct Python, and eligible competitors.
- [x] Expand the experiment matrix to warm/cold singleton, transient depths, fan-out/shared DAG, collections 10/100, scopes, overrides, parameter resolution, sync, and async paths.
- [x] Require latency, Python-call count, allocations, peak/retained memory, freeze cost, and executable-size evidence.
- [x] Add a representative FastAPI non-regression gate before selecting the core strategy.

### Task 2: Make the native decision explicit

**Files:**
- Modify: `specs/proposals/2026-09-02-optional-native-accelerator-proposal.md`

- [x] Require a decision table comparing the original interpreter, optimized Python, native prototype when justified, direct Python, and eligible competitors.
- [x] Require attribution of residual time to interpreter/native-boundary costs before authorizing the Rust prototype.
- [x] Require the handoff recommendation to choose pure Python, optional native acceleration, or stopping native work.

### Task 3: Record call counts as diagnostic evidence

**Files:**
- Modify: `specs/proposals/2026-09-02-competitive-performance-leadership-proposal.md`

- [x] Add Python-call count to diagnostic evidence while keeping latency and workload contracts as the leadership criteria.
- [x] State that diagnostic call counts cannot substitute for application, absolute, or competitive evidence.

### Task 4: Verify and commit

**Files:**
- Review: all three modified proposals and this plan

- [x] Check that Rust remains conditional and optional, the pure-Python core stays complete, and no public API or semantic guarantee changes.
- [x] Check that the workload and metric lists agree across the proposals and contain no aggregate-winner claim.
- [x] Run `uv run ruff format`, `uv run ruff check`, `uv run basedpyright`, `uv run mypy`, and `uv run pytest` in order; expect exit 0 for all five.
- [x] Run `uv run --group docs mkdocs build --strict`; expect exit 0.
- [x] Commit with a conventional documentation subject.
