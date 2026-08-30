# Step 1 verification evidence

Date: 2026-08-30

Measured implementation commit: `9d249c1181b61cb7b65b78d81da467338909ab0b`
Comparison source for the previous cross-loop implementation: `4a241d29b51b1582608f4ac356c756d797940ec1`

Green matrix, mutation, root-cause, benchmark, and graph-sabotage commands ran
at the measured implementation commit. The teardown and mutex failures used
temporary, uncommitted sabotages at
`6e107470390111752d75665b82132ca9bdbbd0e4`; their source and test files are
byte-identical at the measured commit. All sabotage worktrees were clean again
before the green runs.

## Property-based graph validation

The green command exercises all four roadmap properties plus the bounded
cyclic/missing regression:

```console
$ uv run pytest tests/unit/test_graph_properties.py -q
......                                                                   [100%]
6 passed in 3.26s
EXIT=0
```

Each property was then run against one deliberately broken validator.

### Topological order

Sabotage:

```diff
+    return tuple(specs)
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_freeze_returns_a_topological_plan_or_a_depin_error -x -vv
E   AssertionError: out-of-order
E   Falsifying example: test_freeze_returns_a_topological_plan_or_a_depin_error(
E       case=GraphCase(size=4,
E        edges=frozenset({(3, 3)}),
E        scopes=(Scope.SINGLETON, Scope.SINGLETON, Scope.SINGLETON, Scope.SINGLETON),
E        registered=(False, False, False, True),
E        duplicates=frozenset()),
E   )
============================== 1 failed ===============================
EXIT=1
```

### Error hierarchy

Sabotage at the start of `_check_duplicates`:

```diff
+    raise RuntimeError('seeded non-Depin failure')
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_graph_validation_never_leaks_a_non_depin_exception -x -vv
E   AssertionError: unexpected:RuntimeError:seeded non-Depin failure
E   Falsifying example: test_graph_validation_never_leaks_a_non_depin_exception(
E       case=GraphCase(size=1,
E        edges=frozenset(),
E        scopes=(Scope.SINGLETON,),
E        registered=(False,),
E        duplicates=frozenset()),
E   )
============================== 1 failed ===============================
EXIT=1
```

### Acyclic graphs

Sabotage in `_toposort` when a dependency identifier is already visited:

```diff
+    raise CircularDependencyError('seeded false cycle')
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_an_acyclic_graph_never_reports_a_cycle -x -vv
E   AssertionError: circular:seeded false cycle
E   Falsifying example: test_an_acyclic_graph_never_reports_a_cycle(
E       case=GraphCase(size=2,
E        edges=frozenset({(1, 0)}),
E        scopes=(Scope.SINGLETON, Scope.SINGLETON),
E        registered=(True, True),
E        duplicates=frozenset()),
E   )
============================== 1 failed ===============================
EXIT=1
```

### Non-captive graphs

Sabotage:

```diff
-                if dep.scope is Scope.SCOPED:
+                if dep.scope is Scope.SINGLETON:
```

Command and explicit minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_a_graph_without_a_singleton_to_scoped_path_is_not_captive -x -vv
E   AssertionError: captive:captive dependency: singleton GraphNode1 depends on scoped GraphNode0 ...
E   Falsifying explicit example: test_a_graph_without_a_singleton_to_scoped_path_is_not_captive(
E       case=GraphCase(size=2,
E        edges=frozenset({(1, 0)}),
E        scopes=(Scope.SINGLETON, Scope.SINGLETON),
E        registered=(True, True),
E        duplicates=frozenset()),
E   )
============================== 1 failed ===============================
EXIT=1
```

After each sabotage, `git diff --exit-code -- depin/_core/graph.py` returned 0
after restoration.

## Teardown failure preservation

The sabotage removed the `try`/`except` around each `run_sync` and `run_async`
call, making the drains abort on the first failure.

```console
$ uv run pytest tests/unit/test_teardown.py -x -vv
tests/unit/test_teardown.py::test_sync_close_preserves_independent_failures_in_lifo_order FAILED
E   RuntimeError: str failed
============================== 1 failed ===============================
EXIT=1
```

A standalone invocation of the same sabotaged path printed
`RuntimeError: str failed` and `events=['str']`. The drain stopped before
producing the expected `ExceptionGroup`; the later `int` and `bytes` finalizers
were not attempted. Restoring failure collection produced:

```console
$ uv run pytest \
    tests/unit/test_teardown.py::test_sync_close_preserves_independent_failures_in_lifo_order \
    tests/unit/test_teardown.py::test_async_scope_preserves_sync_async_and_generator_failures_in_lifo_order -q
..                                                                       [100%]
2 passed in 0.26s
EXIT=0
```

The assertions pin every exception and the reverse construction order:
`str, int, bytes` for the synchronous root drain and `async, sync, twice` for
the mixed asynchronous drain.

## Free-threaded flight-table mutex

The sabotage removed the root-frame `with self._mutex` from
`ScopeFrame.claim_cached` while leaving the same check-then-create body in
place. The injected rendezvous table forces every thread between the lookup and
write when the mutex is absent.

The implementation plan named the pre-audit `sync_lock_for` seam. The
cross-event-loop fix replaced the separate sync/async lock tables with one
cross-loop flight table, so the pinning test moved to `claim_cached`; it now
guards the same check-create-publish invariant for both sync and async callers.

```console
$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t uv run --no-sync \
    --python /tmp/depin-step1-313t/bin/python pytest \
    tests/unit/test_free_threading.py::test_the_unified_flight_table_survives_concurrent_creation -x -vv
E   assert 32 == 1
============================== 1 failed ===============================
EXIT=1

$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t uv run --no-sync \
    --python /tmp/depin-step1-314t/bin/python pytest \
    tests/unit/test_free_threading.py::test_the_unified_flight_table_survives_concurrent_creation -x -vv
E   assert 32 == 1
============================== 1 failed ===============================
EXIT=1
```

After restoring the mutex, the same commands each reported `1 passed` with
`EXIT=0`. No warning or debug diagnostic appeared in any of the four runs.

## Cross-event-loop singleton root cause

The scenario starts 32 OS threads. Every thread owns an `asyncio.run()` event
loop and resolves the same async singleton. Events and a condition make one
leader suspend inside the provider while all followers join the active flight;
there are no timed sleeps. Each thread crosses the shared barrier immediately
before its one resolution attempt; the later events and condition order leader
and follower phases without relying on the clock.

Against `origin/main` at `4a241d29b51b1582608f4ac356c756d797940ec1`,
the test module from the measured commit was placed on `PYTHONPATH` after the
old source and its standalone worker was invoked with each free-threaded
interpreter:

```console
$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t PYTHONASYNCIODEBUG=1 \
    PYTHONPATH=/tmp/depin-step1-old:/tmp/depin-step1-sabotage/tests/unit \
    /tmp/depin-step1-313t/bin/python -c \
    "import multiprocessing, test_free_threading; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=test_free_threading._run_cross_loop_singleton,args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready',ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit',process.exitcode,'alive',process.is_alive()); parent.close()"
pipe_ready True
failure:RuntimeError('<asyncio.locks.Lock object at 0x4b5ea190190 [locked, waiters:1]> is bound to a different event loop')
process_exit 0 alive False
EXIT=0

$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t PYTHONASYNCIODEBUG=1 \
    PYTHONPATH=/tmp/depin-step1-old:/tmp/depin-step1-sabotage/tests/unit \
    /tmp/depin-step1-314t/bin/python -c \
    "import multiprocessing, test_free_threading; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=test_free_threading._run_cross_loop_singleton,args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready',ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit',process.exitcode,'alive',process.is_alive()); parent.close()"
pipe_ready True
failure:RuntimeError('<asyncio.locks.Lock object at 0x36356330190 [locked, waiters:1]> is bound to a different event loop')
process_exit 0 alive False
EXIT=0
```

The same standalone worker against the measured source returned:

```console
$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t PYTHONASYNCIODEBUG=1 \
    /tmp/depin-step1-313t/bin/python -c \
    "import multiprocessing; from tests.unit.test_free_threading import _run_cross_loop_singleton; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=_run_cross_loop_singleton, args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready', ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit', process.exitcode, 'alive', process.is_alive()); parent.close()"
pipe_ready True
success:constructed=1 resolved=32 identities=1 failures=0
process_exit 0 alive False
EXIT=0

$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t PYTHONASYNCIODEBUG=1 \
    /tmp/depin-step1-314t/bin/python -c \
    "import multiprocessing; from tests.unit.test_free_threading import _run_cross_loop_singleton; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=_run_cross_loop_singleton, args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready', ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit', process.exitcode, 'alive', process.is_alive()); parent.close()"
pipe_ready True
success:constructed=1 resolved=32 identities=1 failures=0
process_exit 0 alive False
EXIT=0
```

Neither debug-enabled green scenario emitted an asyncio warning.

The committed test commands also pass:

```console
$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t uv run --no-sync \
    --python /tmp/depin-step1-313t/bin/python pytest \
    tests/unit/test_free_threading.py::test_async_singleton_is_single_flight_across_event_loops
1 passed in 2.08s
EXIT=0

$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t uv run --no-sync \
    --python /tmp/depin-step1-314t/bin/python pytest \
    tests/unit/test_free_threading.py::test_async_singleton_is_single_flight_across_event_loops
1 passed in 2.40s
EXIT=0
```

## Mutation threshold

Seeded below-threshold fixture:

```console
$ uv run python -m scripts.check_mutation_threshold /tmp/depin-step1-mutation-94.json
mutation score: 94.0% (94 killed, 6 survived, 100 total)
mutation score is 94.0%, below the 95.0% threshold; survivors must be at most 5.0% of decided mutants
EXIT=1
```

Fresh complete run and real gate:

```console
$ uv run mutmut run
Running mutation testing
done
7.46 mutations/second
EXIT=0
$ uv run mutmut export-cicd-stats
Saved CI/CD stats to mutants/mutmut-cicd-stats.json
EXIT=0
$ uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
mutation score: 97.2% (1218 killed, 35 survived, 1253 total)
EXIT=0
```

The exported counters were 1,253 total, 1,218 killed, and 35 survived. The 35
survivors are 2.8% of decided mutants. Every exported inconclusive field—timeout,
suspicious, skipped, no-tests, segfault, and interrupted—is zero. The
mutation-only two-second pytest watchdog turns a deadlock into a killed test
rather than allowing mutmut to classify it as a timeout.

## Benchmark regression

The base and head were measured back to back in detached worktrees using the
same commands as the pull-request job. The base was `d6982107ca69d322d79def60b3d47f077681a4da`
and the head was the measured implementation commit.

```console
$ uv sync --no-default-groups --group bench
$ uv run --no-sync pytest benchmarks --benchmark-only --benchmark-json=/tmp/depin-pr-base.json
8 passed
EXIT=0

$ uv sync --no-default-groups --group bench
$ uv run --no-sync pytest benchmarks --benchmark-only --benchmark-json=/tmp/depin-pr-head.json
8 passed
EXIT=0

$ uv run --no-sync python -m benchmarks.compare /tmp/depin-pr-base.json /tmp/depin-pr-head.json --max-regression=0.25
ok            +0.6%  benchmarks/test_resolution.py::test_call_through_an_inject_wrapper
ok            -2.9%  benchmarks/test_resolution.py::test_freeze_a_chain[1000]
ok            -3.1%  benchmarks/test_resolution.py::test_freeze_a_chain[100]
ok            +0.3%  benchmarks/test_resolution.py::test_freeze_a_chain[10]
ok           +22.7%  benchmarks/test_resolution.py::test_open_and_close_a_scope
ok            +0.1%  benchmarks/test_resolution.py::test_resolve_a_cached_singleton
ok           -65.1%  benchmarks/test_resolution.py::test_resolve_a_transient_chain
ok            +1.1%  benchmarks/test_resolution.py::test_resolve_an_async_singleton
8 benchmark(s) within 25% of the base branch
EXIT=0
```

The head benchmark run emitted no warnings. The base still emits its existing
unknown-`asyncio_mode` warning because `main` does not yet include the benchmark
group fix measured here.

## Per-interpreter coverage

The free-threaded environments contained only the `threads` dependency group;
the three GIL builds used complete isolated development environments. Coverage
was measured independently rather than combined.

| Interpreter | GIL | Command | Tests | `TOTAL` | Coverage | Exit |
| --- | --- | --- | --- | --- | ---: | ---: |
| CPython 3.12.13 | API unavailable | `uv run --python 3.12 pytest --cov=depin --cov-report=term` | 423 passed, 6 skipped | `1214 9 390 18` | 98.32% | 0 |
| CPython 3.13.13 | enabled | `uv run --python 3.13 pytest --cov=depin --cov-report=term` | 423 passed, 6 skipped | `1214 9 390 18` | 98.32% | 0 |
| CPython 3.14.5 | enabled | `uv run --python 3.14 pytest --cov=depin --cov-report=term` | 423 passed, 6 skipped | `1180 9 390 18` | 98.28% | 0 |
| CPython 3.13.13 experimental free-threading | disabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t uv run --no-sync --python /tmp/depin-step1-313t/bin/python pytest tests/unit --cov=depin --cov-report=term` | 377 passed, 0 skipped | `1214 41 390 17` | 96.01% | 0 |
| CPython 3.14.5 free-threading | disabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t uv run --no-sync --python /tmp/depin-step1-314t/bin/python pytest tests/unit --cov=depin --cov-report=term` | 377 passed, 0 skipped | `1180 41 390 17` | 95.92% | 0 |

The blocking-interpreter checks were explicit:

```text
3.12.13 (main, May 10 2026, 19:30:01) [Clang 22.1.3 ]
gil_enabled unavailable
3.13.13 (main, May 10 2026, 19:26:54) [Clang 22.1.3 ]
gil_enabled True
3.14.5 (main, May 10 2026, 19:28:16) [Clang 22.1.3 ]
gil_enabled True
```

The free-threaded interpreter checks were also explicit:

```text
3.13.13 experimental free-threading build (main, May 10 2026, 19:29:57) [Clang 22.1.3 ]
gil_enabled False
3.14.5 free-threading build (main, May 10 2026, 19:27:52) [Clang 22.1.3 ]
GIL_ENABLED False
```

All five independent totals satisfy the repository's 95% coverage gate.

## Final repository audit

The commands in this section ran after evidence commit
`c624dd1976e3cb1b4e3379b381772d9c5080a1b3` existed, with its tracked worktree
clean. The later record-only commit appends this section; it does not claim the
section was already present in the audited commit.

```console
$ uv run ruff format
101 files left unchanged
EXIT=0
$ uv run ruff check
All checks passed!
EXIT=0
$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0
$ uv run mypy
Success: no issues found in 67 source files
EXIT=0
$ uv run pytest
423 passed, 6 skipped
EXIT=0
```

The additional Step 1 checks also passed:

```console
$ uv run --group docs mkdocs build --strict
INFO - Documentation built
EXIT=0
$ uv run --group bench pytest benchmarks --benchmark-only
8 passed
EXIT=0
$ uv run mutmut run
Running mutation testing
done
7.58 mutations/second
EXIT=0
$ uv run mutmut export-cicd-stats
Saved CI/CD stats to mutants/mutmut-cicd-stats.json
EXIT=0
$ uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
mutation score: 97.2% (1218 killed, 35 survived, 1253 total)
EXIT=0
$ git diff --check
EXIT=0
$ git status --short
EXIT=0
```

The exported mutation counters were 1,253 total, 1,218 killed, 35 survived,
and zero inconclusive. The docs command printed Material for MkDocs' upstream
MkDocs 2.0 advisory banner, but no MkDocs diagnostic; strict mode exited 0. The
five repository gates, benchmark suite, and mutation run emitted no warnings
or waivers.
