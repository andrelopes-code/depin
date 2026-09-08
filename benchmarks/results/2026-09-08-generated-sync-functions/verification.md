# Generated synchronous transient verification

## Revisions and datasets

- Prototype-free baseline: `d5d8d032e1de02c0d82e17506a567f7419dd5d6d`.
- Complete generated-runtime matrix: `c196d7c`.
- Security-hardened generated runtime: `2ea58f5f892ad18734d306b00cedaf85fd0c3c8e`.
- Seed: `20260902`; repetitions: 5.
- `base/rep0.json` through `base/rep4.json` and `head/rep0.json` through
  `head/rep4.json` are the raw complete-matrix latency samples. Each side also
  retains `deterministic.json`.
- `safety-hardening/` repeats the baseline and hardened revision for the four
  latency workloads affected by compiler eligibility, source budgets, or the
  generated callable capture. Its deterministic files cover allocation, work,
  retained-memory, and scaling contracts.
- `environment.json` files retain the interpreter, compiler, CPU, load, seed,
  and repetition count. `gate.txt` files retain every budget verdict.

The complete matrix was intentionally not relabelled after the security fix.
The complete dataset proves the generated mechanism at `c196d7c`; the focused
dataset proves that `2ea58f5` preserves the affected results. This keeps the
revision boundary explicit and the raw evidence reproducible.

## Performance collection

The complete matrix used:

```console
uv run --group bench python -m benchmarks.harness.pairs \
  --base-dir /tmp/depin-generated-base/base --head-dir . \
  --repetitions 5 --seed 20260902 --out /tmp/depin-generated-sync-functions
uv run --group bench python -m benchmarks.harness.gate \
  /tmp/depin-generated-sync-functions --budgets benchmarks/budgets.toml
```

It measured `resolve_a_transient_chain` at -86.39% with a
[-86.60%, -85.79%] interval. The accepted absolute medians were 34.405
microseconds for the baseline and 4.687 microseconds for `c196d7c`. The earlier
34.125-microsecond number was a one-run diagnostic, not a member of the paired
dataset.

The hardening rerun selected `resolve_a_transient_chain` and
`freeze_a_chain_of_{10,100,1000}` with the same pair collector, baseline, five
repetitions, and seed. Its gate recorded -86.47% [-87.24%, -85.93%] for
transient resolution and +1.94%, +0.22%, and -0.57% for the three freeze sizes.
All selected latency gates and all deterministic gates passed.

## Correctness and tool gates

The hardened revision passed the repository commit gate in the required order:

```text
ruff format: 333 files left unchanged
ruff check: all checks passed
basedpyright: 0 errors, 0 warnings, 0 notes
mypy: success in 248 source files
pytest: 2575 passed, 6 skipped
mkdocs build --strict: passed
```

Generated-module branch coverage was measured separately:

```console
uv run coverage run --branch -m pytest tests/unit/test_generated_resolution.py -q
uv run coverage report -m depin/_core/generated.py
```

`depin/_core/generated.py` covered 94 of 94 statements and 30 of 30 branches.
The three explicit 1,000-provider sync transient, cold singleton, and async
tests passed together. The focused generated-runtime suite passed 23 tests,
including differential signature-order, varargs, compiler-failure, and shared
DAG budget cases. The separate benchmark contract suite passed all 155 tests.

Security re-verification reproduced both original failures after the fix. The
reordered and varargs signatures stayed on the interpreter. The 16-provider
shared DAG compiled only providers 0 through 8, completed in 0.026 seconds, and
peaked at 1.36 MB instead of the original 170.6 MB.
