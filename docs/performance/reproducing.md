# Reproducing these numbers

Everything on these pages is produced by code in the repository. Your absolute
figures will differ from the published ones — different CPU, different kernel,
different background load — and that is expected. What should reproduce is the
shape: the ratio between `depin` and its direct baseline, the scaling curves, and
the deterministic counts, which do not depend on the host at all.

## Setup

```bash
git clone https://github.com/andrelopes-code/depin
cd depin
uv sync --group bench
```

`benchmarks/` sits outside `testpaths`, so an ordinary `uv run pytest` does not
collect it.

## Run the suite once

```bash
uv run --group bench pytest benchmarks --benchmark-only
```

This prints the usual `pytest-benchmark` table, with one row per workload per
implementation — the `depin` subject and its direct baseline side by side. It is
the quickest way to see the overhead ratio on your own machine.

## Check that the workloads still mean what they claim

```bash
uv run pytest tests/integration/test_workload_contracts.py tests/integration/test_workload_equivalence.py
```

These carry no timing. They assert that every workload states its claim in full,
and that each `depin` implementation and its direct baseline observably do the
same thing: same result, same objects constructed in the same order, same
resources closed in the same order. A benchmark whose baseline has drifted fails
here, before any number is produced.

## Compare two revisions

The same measurement the pull-request gate runs. Point it at two checkouts:

```bash
git worktree add /tmp/base main

uv run --group bench python -m benchmarks.harness.pairs \
    --base-dir /tmp/base --head-dir . --repetitions 5 --out /tmp/measurements

uv run --group bench python -m benchmarks.harness.gate \
    /tmp/measurements --budgets benchmarks/budgets.toml
```

`pairs` measures both revisions in independent processes across five
repetitions, alternating which side runs first. `gate` applies each workload's
budget and exits 0 when everything passed, 1 on a regression, 2 on a malformed
report, and 3 when a result was inconclusive — the case where the estimate is
over budget but its interval still spans it.

Increase `--repetitions` to narrow the intervals. Five is the minimum at which
the gate will reach a verdict at all.

## Confirm the gates actually fail

The repository keeps three deliberate regressions, one per class of protection.
`benchmarks/seeds/README.md` explains each and how to apply it to a scratch
worktree. Applying one and re-running the comparison above should fail the gate
it targets — and, for the allocation and scaling seeds, should leave the latency
gate green, which is why those gates exist.

## Regenerate the results page

```bash
uv run --group bench python -m benchmarks.harness.report benchmarks/results/<dataset>
```

The published [results](results.md) page is exactly this output for the dataset
committed alongside it, and a test asserts they match. A number on that page
cannot have been typed by hand.
