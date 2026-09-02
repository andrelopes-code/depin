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
