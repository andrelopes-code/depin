# Stopped FastAPI minimum-overhead diagnostic

## Decision

**DONE_WITH_CONCERNS: stop the five-repetition collection.** The accepted
2026-09-09 CPU-light direct-baseline increment was 60.7 microseconds. A 25%
reduction requires at most 45.525 microseconds. The first controlled,
counterbalanced pair instead measured 77.975 microseconds in the baseline and
108.542 microseconds in the head.

The head value is 62.8 microseconds above the required maximum and 30.567
microseconds slower than the exact dated baseline pair. A five-repetition run
cannot plausibly turn this into an accepted reduction, so it was not run.

## Provenance

- Baseline: `086adf98459773e3175f4723b2b64e3f47306e42` in the detached,
  locked `/tmp/depin-fastapi-baseline-086adf9` worktree.
- Head: `179bf686eed1838e86429e82ffe479116cacdbce` in the feature worktree.
- Environment, pins, affinity, lock hashes, and exact command:
  `environment.json`.
- Raw pair: `base/rep0.json` and `head/rep0.json`.

## CPU-light result

| Revision | depin p50 | direct p50 | DI-attributable p50 | depin p95 | depin p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 741.696 us | 663.721 us | 77.975 us | 807.366 us | 1,010.372 us |
| Head | 786.621 us | 678.079 us | 108.542 us | 1,015.918 us | 1,378.013 us |

The totals and direct route are semantically paired: both are the same
`/status` application workload and differ only in the depin installation path.
The single pair is diagnostic evidence only; it is not a 95% confidence
interval and it is not a statistical gate input.

## Component and no-injection decomposition

The head collector's raw `rep0.json` preserves the independently measured
component totals: lazy host publication 719.423 us, lazy frame activation and
drain 811.252 us, one-key endpoint program 774.133 us, many-key endpoint
program 763.774 us, request seed read 829.973 us, and async resource close
821.585 us. The installed no-injection route was 716.862 us versus 679.044 us
direct, a 37.818-microsecond increment.

These components isolate the remaining owning areas but are not additive and
cannot be subtracted from endpoint tails. The visible regression is therefore
falsifiable: re-run the same exact paired protocol after reducing the endpoint
program/host-publication path until the CPU-light direct increment is at most
45.525 microseconds, then collect five complete repetitions and evaluate the
authored gate.

## Unsupported comparisons and omitted checks

No confidence interval, throughput comparison, allocation count, peak or
retained memory, startup result, contention result, or competitor leadership
result is claimed. The collector stopped before deterministic observations and
the other four required repetitions. No product target or generated budget was
changed.
