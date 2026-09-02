# Step 7 gate repair — evidence

What was measured while repairing the pull-request performance gate and
completing the coverage its design promised. The normative source is
`specs/2026-09-02-step-7-coverage-completion-design.md`. The proposal's
acceptance criteria are not reopened; `specs/evidence/2026-09-02-step-7-performance.md`
demonstrates them, and its correction section is what this document continues.

Released state at the start: 0.17.1. The gate existed, was blocking, and had
failed its first live run — on a documentation-only pull request.

## The two defects, and what fixed them

Both had one cause: budgets and floors measured on a developer workstation and
applied to a shared runner.

### The two error-path curves are retired

`scale_failing_freeze` claimed a complexity class and reported a constant. On the
runner, with both sides on identical code, it read 7.095, 7.021 and 7.026 ms at
sizes 25, 50 and 100 — flat across a fourfold range — and the difference between
the two identical revisions reached +23.61% against a 15% budget. The cost is
`suggest_candidates` walking `sys.modules` when the error message is built, which
depends on how many modules a process loaded rather than on the graph.

`scale_explain_missing_key` shares the constant, and the audit did not need a new
measurement: the dataset published with 0.17.1 already recorded it at 5.479,
5.503 and 5.444 ms over sizes 10, 12 and 14 — growth 1.00x and 0.99x — while the
number of simple paths through those graphs grows Fibonacci in the size. A curve
that does not move where the quantity it tracks multiplies by about four is not
tracking it.

Both are retired rather than retuned, and the retirement is recorded rather than
performed silently. `benchmarks/harness/unmeasured.py` carries what each claimed,
what invalidated it and what covers the path now; `docs/performance/results.md`
renders that record, so the published page states its absences as well as its
numbers.

### A seed that stopped firing

The design asserted that the failing-freeze path keeps a check "sensitive to the
walk and immune to the constant". Re-running
`benchmarks/seeds/scaling-restore-enumerating-walk.patch` showed it does not.

`tests/unit/test_longest_chain.py::test_failing_freeze_is_not_cubic_in_the_chain_length`
asserted half a second over 400 providers. With the cubic walk restored it
measured **0.42 s** and passed. Measured directly on the same host, freezing that
chain costs **0.022 s** repaired and **0.385 s** seeded — a seventeenfold
regression that the budget did not catch, because the budget was written on a
slower host and the walk had become cheap enough there to fit under it.

Both complexity checks are now growth ratios rather than durations. A ratio
cancels the host, and it cancels the module scan as well, because the scan is the
same constant at both sizes.

| Check | Sizes | Repaired | Seeded | Limit |
| --- | --- | ---: | ---: | ---: |
| Failing freeze | 200 → 400 providers | 1.80 | 5.91 | 3.0 |
| Explaining an unbound key | 16 → 24 nodes | 1.00 | 24.94 | 2.0 |

The measurements behind them, best of three passes per size:

| | 100 | 200 | 400 |
| --- | ---: | ---: | ---: |
| failing freeze, repaired | 11.15 ms | 11.25 ms | 20.29 ms |
| failing freeze, seeded | 18.24 ms | 67.31 ms | 397.54 ms |

The repaired row is why the retired curve's sizes were wrong as well as its
budget: at 100 and 200 providers the walk is invisible under an 11 ms constant,
and only at 400 does it carry the cost.

### The sample-quality floor is derived per workload

`MINIMUM_LATENCY_ROUNDS = 120` was one number applied to every workload. It bound
`build_the_graph_view` to 120 rounds and 0.408 s on the runner, under the half
second the rule requires, and it did not bind `resolve_a_collection_of_10` at
all, which ran 485 rounds for 0.007 s.

The floor is now `reduce.rounds_for`, applied by the timing shell per case:

    min(MINIMUM_ROUNDS, ceil(HOST_MARGIN x MINIMUM_SECONDS / median))

The median comes from the accepted dataset, which already records it. `qualifies`
is satisfied by either of its two branches, so the cheapest floor that carries it
is the smaller of the two. `HOST_MARGIN = 4` is there because the floor is derived
on one host and applied on another, and the runner is not uniformly slower —
`build_the_graph_view` measured 5.9 ms on the reference host and 3.4 ms on the
runner.

**Measured on the runner, over ten runs of identical code: zero repetitions fell
under the sample-quality minimum.** The delivered gate produced three
`no-verdict` workloads on the same job.

## Calibration on both hosts

`benchmarks/harness/calibrate.py` derives the budget file from a collection in
which both sides are the same revision. The runs in such a collection are
exchangeable, so ten of them carry 1512 trials of the paired statistic: every
split into two halves, six orderings each, from a fixed seed. `budgets.toml` is
that command's output and is no longer edited by hand.

The `Calibrate` workflow runs it on the pull-request runner. That is where the
committed budgets come from, because that is where the gate runs and where its
false alarms are paid for.

Both hosts were calibrated. For 37 of the 41 latency workloads the two agree
within about two points. Four do not:

| Workload | reference host | runner | committed budget |
| --- | ---: | ---: | ---: |
| `freeze_a_chain_missing_a_provider_of_100` | 5.44% | 18.72% | 38% |
| `freeze_a_chain_missing_a_provider_of_50` | 4.01% | 15.73% | 32% |
| `explain_an_unbound_key_of_16` | 3.70% | 15.28% | 31% |
| `explain_an_unbound_key_of_20` | 3.60% | 12.46% | 25% |
| `resolve_a_sync_resource_with_teardown` | 3.17% | 7.85% | 16% |

The first four are the error paths, and the constant they carry is the same
`sys.modules` walk that invalidated the retired curves. On a shared runner a
memory-walking loop is three to four times noisier than a compute loop, and the
formula turns that into budgets wider than the uniform 25% this whole system
replaced.

Those four budgets are honest and nearly useless. They are published as measured
rather than trimmed, and what actually protects those paths is stated instead:
the two complexity ratio checks above, which the seed fails by factors of two and
twelve, and the deterministic work counts, which cannot move at all. A reader who
wants the number can see 18.72% in the justification line beside the 38%.

The remaining 36 workloads carry budgets between 5% and 11%.

## The coverage the design promised

Six latency workloads were added to tier 1 and two curves to tier 4. Reference-host
figures, all host-specific:

| Workload | depin | direct | Read as |
| --- | ---: | ---: | --- |
| `resolve_with_no_active_override` | 1.815 µs | 96.0 ns | the control the next two are read against |
| `resolve_through_an_active_override` | 3.844 µs | 130.5 ns | an active override costs **+2.03 µs**, more than doubling a cached resolution |
| `resolve_a_generic_key` | 5.931 µs | — | a parameterised key costs **+4.12 µs** per resolution, 3.3x a plain class key |
| `construct_a_singleton_for_the_first_time` | 5.417 µs | 380.9 ns | cold construction adds about 3.6 µs over the warm lookup |
| `resolve_a_sync_resource_with_teardown` | 12.901 µs | 1.577 µs | 8.2x a handwritten context manager doing the same work |
| `call_through_an_inject_wrapper_with_explicit_arguments` | 6.720 µs | 176.8 ns | a caller-supplied argument adds **+1.09 µs** over `call_through_an_inject_wrapper` |

The override pair is the one the design asked for first, and it answers the
question it was added for: `overrides.active` runs on every resolution, and what
it costs when it fires is more than the whole resolution costs when it does not.

The generic-key figure is the finding that came out of the additions.
`resolve_a_generic_key` is 3.3 times a plain class key on the resolution path,
where the only previous measurement of that cost was at freeze time. It is
recorded here and routed to Step 8 rather than repaired: this release is a gate
repair.

The two new curves:

| Curve | Sizes | Growth |
| --- | --- | --- |
| `scale_async_teardown` | 10, 20, 40 | 1.58x, 1.73x |
| `scale_override_nesting` | 8, 32, 128 | 1.71x, 2.76x |

`scale_override_nesting` resolves through a stack of frames none of which names
the key, which is the shape a resolution takes inside a test that has overridden
something else. Solving the two points gives about **79 ns per standing override
frame** over a fixed 2.04 µs.

Two proposal cases are refused rather than measured, and both refusals name what
would be needed instead — concurrency benchmarking that does not measure its own
synchronisation, and a soak that does not belong in a blocking gate. They are in
`benchmarks/harness/unmeasured.py` and on the published page.

CPU time and tail quantiles are now collected and published for the application
tier. `pytest-benchmark` makes one further untimed call after its rounds and
returns its result, so the `Cost` a tier 3 callable returns is read there and
filed into `extra_info`; the round array the report already carries is where p95
and p99 come from. Neither is gated, and the page says why.

## The republished dataset

`benchmarks/results/2026-09-02/` was regenerated on the reference host, and
`docs/performance/results.md` is its render. The series is continuous: a cached
resolution moved 1.759 → 1.817 µs and a 20-deep transient chain 34.548 → 34.752
µs, which is inside the spread either dataset records.

That continuity required a correction. The first regeneration ran on the
interpreter the working checkout happened to hold — CPython 3.12.3 built with
GCC — where the previously published dataset and the runner both use 3.12.13
built with Clang. It moved a cached resolution by +19% for no reason connected to
this change. The collection was repeated on the matching interpreter and the
first one discarded.

**The host was not quiet.** Other work was running throughout and could not be
stopped, and the recorded load average is 2.41 — the same condition the 0.17.1
dataset records at 2.43, so the two are comparable to each other rather than to
an idle machine. This is why the blocking budgets are taken from the runner and
not from here: the reference host produces absolute figures, which are labelled
host-specific and whose medians are robust to load, and it does not produce the
numbers the gate enforces.

## The seeds, re-run

Three seeded regressions, each applied to a scratch worktree, measured against
the unmodified tree, gated against the committed runner-derived budgets.

**Allocations** — exit 1, from a single repetition:

```
fail  allocations  allocations_of_a_cached_singleton_resolution: size 1168 -> 1352 (+15.75%) budget 0.0%
fail  allocations  allocations_of_a_request_shaped_scope:        blocks 27 -> 32 (+18.52%) budget 0.0%
fail  allocations  allocations_of_a_scope_cycle:                 size 6240 -> 9800 (+57.05%) budget 0.0%
```

**Scaling** — exit 1. The curves this seed used to fail no longer exist, and it
fails anyway, on the fixed-size latency workloads over the same paths:

```
fail  latency  explain_an_unbound_key_of_20:             +517.18% [+484.09%, +530.82%] budget 25.0% n=5
fail  latency  freeze_a_chain_missing_a_provider_of_100:  +71.45% [ +65.78%,  +95.55%] budget 38.0% n=5
fail  latency  explain_an_unbound_key_of_16:              +68.39% [ +64.02%,  +69.47%] budget 31.0% n=5
```

Those are the four workloads whose budgets the runner's noise pushed to 25–38%,
and the seed clears them by two to twenty times. The two complexity ratio checks
fail on the same patch at 5.58 against 3.0 and 24.94 against 2.0. The path is
covered from both directions.

**Latency** — exit 1, over five paired repetitions: five latency failures, three
inconclusive, and all five work counts:

```
fail          latency  resolve_a_generic_key:                                 +29.26% [+20.26%, +39.61%] budget 5.0%
fail          latency  resolve_singleton_through_a_two_deep_decoration_chain:  +20.06% [+16.46%, +22.05%] budget 5.0%
fail          latency  resolve_with_no_active_override:                        +16.92% [ +9.43%, +18.52%] budget 5.0%
fail          latency  resolve_cached_singleton_through_an_alias:              +15.42% [+11.56%, +19.19%] budget 5.0%
fail          latency  resolve_cached_singleton:                               +14.17% [ +9.93%, +18.77%] budget 5.0%
inconclusive  latency  construct_a_singleton_for_the_first_time:               +11.42% [ +0.33%, +13.01%] budget 5.0%
fail          work     allocations_of_a_cached_singleton_resolution: 9 -> 10   (+11.11%) budget 0.0%
```

Two of the new workloads are among the detectors, which is a small piece of
evidence that the coverage additions carry their weight rather than only their
claims.

### A false alarm the same run produced

`scale_resolve_fan_out` failed the latency seed at +37.27% against 15%. It is not
a complexity change. The measured curve on the head side reads 19.81, 53.42 and
75.01 µs against a base of 18.62, 36.58 and 67.32: the middle point is inflated
by about 46% and its neighbours by 6% and 11%, which is a contaminated
measurement on a loaded host, not a shape.

The scaling verdict is a point estimate over the worst size-to-size difference,
with no interval and no repetition, so one bad point fails it. On the runner's
null collection every scaling curve passed. Recorded as a property of the check
worth revisiting rather than repaired here — an interval over repeated curves is
a design change, and this release is a repair.

## The gate on a real pull request

The repair's own pull request is the second live run of the gate. The first pass
returned six `no-verdict` verdicts and exit 3, escalated once at double the
repetitions, and passed.

Every one of those six came from the base side, which is `main` — a revision
whose timing shell has no per-workload floor. The collection command is the head
revision's, so the base ran without the flag the old code relied on and without
the markers the new code applies. The escalation absorbed it, and it does not
recur once this lands: from the next pull request onward both sides carry the
derived floor.

## A duplicated measurement, removed

`Claim.noise` declared the dispersion band a workload was measured into. Nothing
read it, and it disagreed with the calibration for **25 of the 41** latency
workloads — systematically pessimistic, declaring `high` where the measurement
said `low`.

Two copies of a measured value cannot both be authoritative, and the authoritative
one is generated: `budgets.toml` carries the band beside the p99 that produced it,
in the environment it was measured in. The field is removed rather than
synchronised, and `NoiseClass` now says where the band lives.

## Gates

Measured on the reference host, at the commit this document accompanies.

| Gate | Result |
| --- | --- |
| `ruff format` | 301 files unchanged |
| `ruff check` | clean |
| `basedpyright` strict | 0 errors over 186 files |
| `mypy` strict | clean over 186 files |
| `pytest` | 2361 passed, 6 skipped |
| coverage over `depin/` | 99% against a 95% floor |
| `mkdocs build --strict` | built |
| gate over the reference null collection | 62 verdicts, all pass, exit 0 |
| gate over the runner null collection | 62 verdicts, all pass, exit 0 |

## What this did not do

- **The generic-key resolution cost was not repaired.** It was measured for the
  first time and routed to Step 8, which owns the resolution path.
- **The scaling verdict was not given an interval.** The false alarm above says
  it should have one; giving it one changes what a scaling result means, and
  that needs its own design.
- **The four wide error-path budgets were not trimmed.** A budget is what the
  measurement supports. Making them useful means taking the module scan out of
  the timed region, which changes what those workloads claim.
- **No competitor number is published**, and no absolute latency budget is
  gated. Both remain as Step 7 left them.
