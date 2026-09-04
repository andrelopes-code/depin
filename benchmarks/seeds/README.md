# Seeded regressions

A gate that has never failed is not known to work. These patches make it fail on
purpose, one per class of protection, so the sensitivity of each check is
demonstrated rather than assumed.

Each patch introduces a plausible regression — the kind a refactor produces by
accident, not a deliberate sabotage — and each targets a different gate.

| Patch | What it does | Which gate should catch it |
| --- | --- | --- |
| `latency-eager-error-message.patch` | Formats the missing-provider message on every lookup instead of only when the lookup fails | Latency, on the frequent resolution workloads |
| `allocation-per-resolution-dict.patch` | Builds a throwaway dictionary on every cached resolution | Allocations, exactly, from a single repetition — a count has no dispersion to average away |
| `scaling-restore-enumerating-walk.patch` | Restores the pre-repair chain search, which is cubic on the failing-freeze path and exponential on the missing-key path | The two complexity checks in `tests/unit/test_longest_chain.py`, which compare growth between two sizes |

The third one moved. It used to be caught by the `scale_failing_freeze` and
`scale_explain_missing_key` curves, and both were retired once the repair left
their paths dominated by a size-independent constant —
`benchmarks/harness/unmeasured.py` carries that record. Re-running the seed
against the retired curves is what showed the replacement was not yet in place:
the wall-clock budget that stood in for them passed the seeded cubic walk at
0.42 s against half a second, on a host faster than the one it was written on.
Both checks now compare two sizes, which cancels the host and the constant
together, and both fail on the seed by a factor of two or more.

## Applying one

Never apply a seed to a checkout you intend to commit from. Use a scratch
worktree:

```bash
git worktree add /tmp/seeded HEAD
git -C /tmp/seeded apply "$PWD/benchmarks/seeds/<patch>"
```

Measure that worktree against the unmodified one, then remove it:

```bash
git worktree remove --force /tmp/seeded
```

The [performance methodology](../../docs/performance/methodology.md) and
[reproducing guide](../../docs/performance/reproducing.md) describe how to
collect and interpret a seed verdict.

## Competitive cached lookup

`competitive-cached-lookup.patch` adds one container-owned dictionary allocation
and lookup on every warm cached singleton hit. It was measured in a temporary
clone at `2daaf7ceb82764a0ba44e5ef4c4b4c39048b0a25`, using CPU 0, the v3 archived
baseline, and the v3 calibration (schema 1, provenance fingerprint
`643844979a968bf143d3686a5f53bd842e0f71295e8f6f4873dbfd9116579405`).

The seeded collector was `PYTHONPATH=/tmp/task12-seed-v3c.9sWpLf/seed taskset
-c 0 timeout 1200s /home/dreco/.config/superpowers/worktrees/depin/
performance-leadership-execution/.venv/bin/python -m
benchmarks.comparison.collection collect --workload resolve_cached_singleton
--repetitions 5 --timeout-seconds 1200 --out
/tmp/task12-seed-v3c.9sWpLf/seed-result --baseline-dir
/tmp/task12-v3.l6PIqv/baseline --baseline-revision
4ad63e77bd21eefab15f1dde44c7e62460533da7 --budgets benchmarks/budgets.toml`
(exit 0). The evaluator against
`/tmp/task12-v3.l6PIqv/calibration-pinned.json` and the same budgets exited 3
because focused evidence omits other target rows; the cached verdict itself was
`loss`.

The post-removal collector at
`/tmp/task12-seed-v3.cPvvkW/removed-result-v2/comparison.json` also exited 0,
and its focused evaluator exited 3 with cached verdict `loss`. Removing the seed
reduced the depin median from 1.88406556845 to 1.73703301698 microseconds
(8.465%) and reduced the excess ratio to Dependency Injector by 119.616
percentage points. Both exceed the calibrated 1.5% allowance. The unchanged
`loss` category is expected: competitive loss has precedence, so the proof is
the reversible measured degradation rather than a nonexistent category change.
