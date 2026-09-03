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

The evidence report `specs/evidence/2026-09-02-step-7-performance.md` records the
verdict each seed produced, and the verdict after it was removed.

## Competitive cached lookup

`competitive-cached-lookup.patch` adds one container-owned dictionary allocation
and lookup on the warm cached singleton path. A focused five-repetition collection
reported `loss` for `resolve_cached_singleton`; the unseeded accepted comparison
also reports `loss`, because competitive loss takes precedence over the absolute
and secondary decisions. The seed still changed the measured median from
1.804 microseconds after removal to 1.867 microseconds while applied. Removing it
reduced the median by 3.379% and the ratio to Dependency Injector by 3.820%, both
above the calibrated 2.0% allowance.

The temporary clone commands were `git apply benchmarks/seeds/competitive-cached-lookup.patch`,
the focused `benchmarks.harness.comparison collect --workload resolve_cached_singleton`
command with five repetitions, and `git revert 81dff6a09dca2819d3903216b7df9f65485ff551`.

The seeded collector command was
`timeout 1260s python -m benchmarks.harness.comparison collect --workload resolve_cached_singleton --repetitions 5 --timeout-seconds 1200 --out /tmp/tmp.2VTkNB1dtZ/seed-result-2 --baseline-dir /tmp/tmp.UlAiP8fmyT/baseline --baseline-revision 4ad63e77bd21eefab15f1dde44c7e62460533da7 --budgets benchmarks/budgets.toml` (exit 0).
Its evaluator command was `timeout 120s python -m benchmarks.harness.leadership evaluate /tmp/tmp.2VTkNB1dtZ/seed-result-2/comparison.json --calibration /tmp/tmp.UlAiP8fmyT/calibration.json --budgets benchmarks/budgets.toml` (exit 3 because focused evidence omits other targets; cached verdict `loss`).
After removal, the same collector with `--out /tmp/tmp.2VTkNB1dtZ/seed-removed-result`
exited 0; its evaluator command, with that dataset path, exited 3 and restored the
cached verdict to the original unseeded `loss`. The seeded category is also `loss`
because competitive loss has precedence; the restoration proof is the >2% median
and ratio reduction, not a nonexistent categorical transition.
