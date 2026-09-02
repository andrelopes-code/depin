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
| `scaling-restore-enumerating-walk.patch` | Restores the pre-repair chain search, which is cubic on the failing-freeze path and exponential on the missing-key path | Scaling. The fixed-size latency workloads stay green, which is the point |

The third is the one that shows why the scaling gate exists: a complexity change
is invisible to a benchmark that only ever measures one size.

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
