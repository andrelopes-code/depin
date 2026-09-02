# Step 7 baseline — the benchmark suite, its noise, and what it can support

Date: 2026-09-02
Commit measured: `3c2ed50`
Status: input to the Step 7 design specification

The proposal
`specs/proposals/2026-08-31-performance-evidence-and-regression-proposal.md`
requires a fresh audit before any design choice: "It should not assume that the
point-in-time numbers in this proposal remain valid." This document is that
audit. Every number in it was measured on 2026-09-02 against `3c2ed50`.

## Measurement host

| Property | Value |
| --- | --- |
| CPU | Intel Xeon E5-2683 v4 @ 2.10 GHz, 4 vCPU, 1 thread per core |
| Memory | 31 GiB |
| Kernel | Linux 6.8.0-138-generic, glibc 2.39 |
| Python | CPython 3.12.3, GIL enabled |
| uv | 0.11.13 |
| Load average at the start of measurement | 1.84 over 4 cores |

**This host is not idle and is not a controlled benchmark machine.** It is a
developer workstation carrying other work. That is not a defect in the
measurement so much as the fact the design has to answer: the project does not
own a quiet machine, and the proposal's question "what stable environment should
produce public absolute results?" cannot be answered with one it does not have.

Every absolute figure below is therefore host-specific and is reported as such.
The ratios, the complexity classes, and the noise structure are the parts that
transfer.

## The suite as it stands

`benchmarks/` holds **24** `pytest-benchmark` cases — the proposal counted 23,
and one has been added since. One complete run takes **22.6 s**.

The pull-request job measures `origin/<base>` and the head commit on one runner,
back to back, and fails when any benchmark common to both is more than 25%
slower on the head side. `benchmarks/compare.py` reports new and removed
benchmarks without failing on them, and fails when no benchmark appears in both.

### Workload inventory and claim classification

What each existing case can be read as saying, before any change.

| Case | Timed region | Can support |
| --- | --- | --- |
| `freeze_a_chain[10/100/1000]` | `freeze()` alone; the container is built outside | Absolute startup cost, once it carries a contract. There is no direct-Python counterpart: hand-wiring has no validation step to compare against |
| `freeze_a_chain_of_generic_keys[10/100/1000]` | as above | The incremental cost of a parameterised key, paired against the plain chain at the same size |
| `freeze_a_chain_with_every_node_decorated[10/100/1000]` | as above | The incremental cost of the decoration fold, paired at the same size |
| `warmup_a_chain` | `warmup()` alone; a fresh freeze per round via `pedantic(setup=...)` | Absolute startup cost of constructing every singleton |
| `resolve_a_cached_singleton` | one `resolve()` on a warm cache | The recurring hot path, once a direct baseline exists |
| `resolve_a_cached_singleton_through_an_alias` | as above, through an alias | The alias hop, paired against the previous case at the same graph size |
| `resolve_a_singleton_through_a_two_deep_decoration_chain` | as above, two decorators | **Correction required.** Its docstring compares it with `resolve_a_cached_singleton`, which uses a 100-node graph, while this case uses a 1-node graph |
| `resolve_a_collection[10/100]` | one `resolve()` of a `list[Element]` | Collection cost by member count, once a direct baseline exists |
| `resolve_a_transient_chain` | one `resolve()` of a 20-deep transient chain | Construction overhead, once a direct baseline exists |
| `open_and_close_a_scope` | scope entry, one resolve, teardown | **Regression only.** The noisiest case in the suite; see below |
| `call_through_an_inject_wrapper` | one call through `@inject` | Wrapper dispatch, once a direct baseline exists |
| `open_a_request_shaped_scope` | scope entry, seed, resolve | The per-request shape, once a direct baseline exists |
| `resolve_an_async_singleton` | `run_until_complete(aresolve(...))` | **Correction required.** 82% of the timed region is the event loop; see below |
| `build_the_graph_view` | `graph()` over 1000 nodes | Diagnostic cost, published separately from resolution |
| `explain_a_deep_chain` | `explain()` over a 1000-node linear chain | **Coverage gap.** It never exercises the subtree-elision guard; see below |
| `explain_a_deep_chain_with_every_node_decorated` | as above, decorated | Diagnostic cost of a decoration chain, paired at the same size |
| `export_a_large_graph_as_dot` | `dot()` over 1000 nodes | Export cost |

Absent from the suite entirely: every error path, memory and allocation
behaviour, any end-to-end application, any scaling curve, any concurrency
measurement, and any direct-Python baseline whatsoever.

## Noise

### The null experiment

Ten complete runs of the suite, in ten independent processes, against identical
code. Under the null hypothesis every difference between two runs is noise.

Dispersion of the per-benchmark run mean across the ten processes ranges from
**0.9%** (`export_a_large_graph_as_dot`) to **7.0%**
(`open_and_close_a_scope`) coefficient of variation.

Simulating the current gate over all 90 ordered pairs of those runs:

- the 25% threshold fired on **0 of 90** pairs;
- the worst single-benchmark excursion under the null was **+18.6%**.

The current gate is therefore not prone to false alarms on this host. Its defect
is the other one: **a uniform 25% threshold sits just above the noisiest
workload and roughly twenty times above the quietest.** A 20% regression in
`export_a_large_graph_as_dot`, whose run-to-run spread is 2.5%, passes silently.
This is the measured form of the proposal's claim that "a single global 25%
threshold is too coarse as a long-term contract".

### What pairing buys

Repeating the simulation with the protocol the proposal requires — R independent
process-level repetitions per side, paired by repetition, the statistic being the
median of the paired log ratios — over every split of the ten exchangeable runs
into five and five, four random orderings each (1008 trials per benchmark):

| | worst null excursion | false alarms at 5% | at 10% | at 15% |
| --- | ---: | ---: | ---: | ---: |
| one run against one run | +18.6% | 7.45% | 2.13% | 0.32% |
| five paired repetitions | +14.4% | 1.10% | 0.49% | 0.00% |

Per benchmark, the 99th percentile of the null statistic falls from a single-pair
range of 2.5%–18.6% to a paired range of **1.7%–13.8%**. For 23 of the 24 cases
pairing roughly halves the excursion; `explain_a_deep_chain` falls from 6.4% to
2.6%, `resolve_a_transient_chain` from 13.7% to 3.0%.

The 24th is `open_and_close_a_scope`, which stays at 13.8%. Its dispersion is not
the between-run common-mode drift that pairing removes.

### A rejected mitigation

Hypothesis: `open_and_close_a_scope` is destabilised by heap state left behind by
the 1000-node cases that run before it, because it constructs and tears down 20
scoped objects per round.

Two experiments, both negative:

- `--benchmark-disable-gc` over eight runs made it **worse**: coefficient of
  variation 5.9% against 3.5%, median 216.1 µs against 204.9 µs. Suppressing
  collection lets garbage accumulate across rounds.
- An autouse fixture calling `gc.collect()` before and after every benchmark, six
  runs of the full suite, produced no improvement on the target case (7.3%
  against 7.0%) and degraded several others.

Neither mitigation is adopted. The dispersion is treated as a property of the
workload, and the design gives it a budget justified by its measured band rather
than a mitigation that the data does not support.

## Timing boundaries

### Graph size does not affect a cached lookup

Median nanoseconds per `resolve()` on a warm cache, by graph size:

| nodes | 1 | 10 | 100 | 300 |
| --- | ---: | ---: | ---: | ---: |
| ns per resolve | 2021 | 1970 | 2033 | 1992 |

Flat within 3%. This settles the
`resolve_a_singleton_through_a_two_deep_decoration_chain` mismatch: the
comparison its docstring draws is sound in substance, because the graph-size
difference it never controlled for does not move the number. The correction is
to control it anyway, so the case does not depend on a fact stated nowhere.

### The async case is mostly the event loop

| Timed region | Median |
| --- | ---: |
| `run_until_complete(aresolve(Pool))` | 19.614 µs |
| `run_until_complete(bare_coroutine())` | 16.093 µs |

**82% of the timed region is `asyncio`, not `depin`.** The case is a valid
regression alarm and cannot support an absolute statement about async resolution
cost. The difference — 3.5 µs — is the part attributable to `depin`, and it is
only visible when the bare-coroutine baseline is measured beside it.

### The elision guard is not covered

`render_tree` elides an already-expanded subtree with `if ident in expanded`.
`explain_a_deep_chain` renders `build_chain(1000)`, which is strictly linear, so
no node is reached twice. The rendered output carries **0 occurrences** of
`(shown above)` across its 1000 lines: the guard never executes, and removing it
could not change this benchmark's result. Per-path expansion only blows up on a
diamond.

## The three routed findings

All three are confirmed against `3c2ed50`. None needs re-deriving.

### Cubic failing freeze

Linear chain of n providers whose deepest node requires an unbound key, timed
through `Container.freeze()` raising `MissingProviderError`; best of three, gc
collected between rounds.

| nodes | 50 | 100 | 200 | 400 |
| --- | ---: | ---: | ---: | ---: |
| seconds | 0.0090 | 0.0320 | 0.1927 | 1.3799 |
| ratio to previous | — | 3.54 | 6.03 | 7.16 |

The roadmap recorded 188 ms at 200 and 1386 ms at 400. Reproduced within 3%.
Twice the nodes for seven times the time is the cubic signature.

### Exponential missing-key walk

`FrozenContainer.explain(key)` for an unbound key over a fan-in-2 layered DAG,
where the count of simple paths is Fibonacci in n.

| nodes | 14 | 16 | 18 | 20 | 22 | 24 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| seconds | 0.0067 | 0.0121 | 0.0279 | 0.0699 | 0.1860 | 0.5032 |

The roadmap recorded 0.007, 0.033, 0.081 and 0.210 at 14, 18, 20 and 22.
Reproduced, and extended one step to half a second at 24 nodes.

The walk runs for any key the graph does not bind, whether or not an edge points
at it.

### The elision benchmark

Confirmed above: zero elisions over the shape it measures.

## Two findings this audit adds

### Cold resolution has a depth cliff at 332 providers

`FrozenContainer.resolve()` recurses through `_resolve_sync` →
`_resolve_params_sync` → `_resolve_sync`, roughly three stack frames per
dependency. Binary search over chain depth, on the default recursion limit of
1000:

| Scope | Deepest chain a cold `resolve()` survives |
| --- | ---: |
| singleton | 332 |
| transient | 332 |

The number is a frame budget divided by frames per provider, so it moves with
whatever stack is already spent when `resolve()` is called: 332 from a bare
interpreter, 331 under `pytest`. The cliff is the property; the integer is not.

`freeze()` accepts a 1000-provider chain and validates it in linear time.
`warmup()` succeeds on the same graph, because it constructs in topological order
and every resolve then finds its dependency already cached. A cold `resolve()` of
the deep end raises `RecursionError`.

So a graph `freeze()` accepts can be one the runtime cannot resolve, and the
comment in `render.py` describing "a chain of a thousand providers" as "a
supported graph" holds for rendering and validation but not for cold resolution.

This is a scaling cliff, which is what the proposal's fourth tier exists to find.
It is not a performance defect, and repairing it means making resolution
iterative — a change to the runtime's structure, to the async path, to teardown
ordering and to overrides. **Routed to Step 8**, which owns what the public
surface commits to, and which is where the question "what dependency depth does
`depin` support?" belongs. Step 7 pins the measured cliff with a scaling workload
so that it cannot move unnoticed.

### The cached resolution path costs about 2 µs, spread across the call graph

| Operation | Median |
| --- | ---: |
| `resolve()` of a cached singleton | 2.17 µs |
| direct attribute access on a held object | 0.06 µs |
| 20-deep transient chain through `depin` | 43.8 µs |
| the same chain constructed explicitly | 5.35 µs |

The transient ratio is **8.2x**, an increment of 38.5 µs over 20 constructions,
or roughly 1.9 µs per node — the same per-resolution cost the cached case shows.

`cProfile` over 200,000 cached resolutions records **2.6 million calls, thirteen
per resolution**, distributed across `resolve` → `_lookup` → `_lookup_optional` →
`is_provider_key` → `overrides.active` → `_resolve_sync` → `_resolve_cached_sync`
→ `claim_cached`. No single function holds more than 15% of the profiled time.

There is no hotspot to remove. The cost is the depth of the call graph itself,
plus one mutex acquisition and one `ContextVar` read per resolution — and both of
those carry guarantees: the mutex is what makes claim-or-join atomic on a
free-threaded build, and the `ContextVar` is what makes `override` reach a key
everywhere it appears rather than only at the top-level lookup.

The structural remedy is compiling the plan into per-key closures. Step 8 already
reserves the right to do exactly that, "only on evidence". This is that evidence.
It is recorded here and not acted on in Step 7, because it restructures the
runtime rather than measuring it.

## Raw artifacts

One `--benchmark-json` report for the current 24-case suite is **21 MB**: the
format stores every round of every benchmark, and the fastest cases run about
100,000 rounds. Ten runs are 178 MB.

Committing round-level JSON per published dataset is not viable, which answers
the proposal's storage question without needing a policy argument. The published
raw data has to be the observations the statistics are actually computed from —
one aggregate per repetition per workload — with the round-level report kept as a
transient CI artifact and regenerable from the harness.

## Public statements today

`grep` over `README.md`, `docs/` and `mkdocs.yml` finds **no performance claim of
any kind**. `CONTRIBUTING.md` explains how to run the suite and states that the
tolerance lives in `benchmarks/compare.py`.

Nothing published has to be corrected or withdrawn. The design starts from
silence rather than from a claim.
