# Step 1 verification evidence

Date: 2026-08-30

Measured source commit: `3d45a48646d6528916344f7811af8fbc8a2fba9b`
Comparison source for the previous cross-loop implementation: `4a241d29b51b1582608f4ac356c756d797940ec1`

All commands ran from an isolated worktree at the measured commit unless a
different worktree is named. Failure commands used temporary, uncommitted
sabotages and the worktrees were clean again before the green runs.

## Property-based graph validation

The green command exercises all four roadmap properties plus the bounded
cyclic/missing regression:

```console
$ uv run pytest tests/unit/test_graph_properties.py -q
.....                                                                    [100%]
5 passed in 3.91s
EXIT=0
```

Each property was then run against one deliberately broken validator.

### Topological order

Sabotage:

```diff
-    return tuple(ordered)
+    return tuple(reversed(ordered))
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_freeze_returns_a_topological_plan_or_a_depin_error -q
E   AssertionError: out-of-order
E   Falsifying example: test_freeze_returns_a_topological_plan_or_a_depin_error(
E       case=GraphCase(size=3,
E        edges=frozenset({(0, 2)}),
E        scopes=(Scope.SINGLETON, Scope.SINGLETON, Scope.SINGLETON),
E        registered=(True, False, True),
E        duplicates=frozenset()),
E   )
1 failed in 4.23s
EXIT=1
```

### Error hierarchy

Sabotage immediately after `build_specs(records)`:

```diff
+    raise ValueError('deliberately escaped validator error')
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_graph_validation_never_leaks_a_non_depin_exception -q
E   AssertionError: unexpected:ValueError:deliberately escaped validator error
E   Falsifying example: test_graph_validation_never_leaks_a_non_depin_exception(
E       case=GraphCase(size=1,
E        edges=frozenset(),
E        scopes=(Scope.SINGLETON,),
E        registered=(False,),
E        duplicates=frozenset()),
E   )
1 failed in 3.80s
EXIT=1
```

### Acyclic graphs

Sabotage at the start of `_toposort`:

```diff
+    raise CircularDependencyError('deliberately reported cycle')
```

Command and minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_an_acyclic_graph_never_reports_a_cycle -q
E   AssertionError: circular:deliberately reported cycle
E   Falsifying example: test_an_acyclic_graph_never_reports_a_cycle(
E       case=GraphCase(size=1,
E        edges=frozenset(),
E        scopes=(Scope.SINGLETON,),
E        registered=(True,),
E        duplicates=frozenset()),
E   )
1 failed in 3.06s
EXIT=1
```

### Non-captive graphs

Sabotage:

```diff
-                if dep.scope is Scope.SCOPED:
+                if dep.scope is not Scope.SCOPED:
```

Command and explicit minimized failure:

```console
$ uv run pytest tests/unit/test_graph_properties.py::test_a_graph_without_a_singleton_to_scoped_path_is_not_captive -q
E   AssertionError: captive:captive dependency: singleton GraphNode1 depends on scoped GraphNode0 ...
E   Falsifying explicit example: test_a_graph_without_a_singleton_to_scoped_path_is_not_captive(
E       case=GraphCase(size=2,
E        edges=frozenset({(1, 0)}),
E        scopes=(Scope.SINGLETON, Scope.SINGLETON),
E        registered=(True, True),
E        duplicates=frozenset()),
E   )
1 failed in 0.45s
EXIT=1
```

## Teardown failure preservation

The sabotage removed the `try`/`except` around each `run_sync` and `run_async`
call, making the drains abort on the first failure.

```console
$ uv run pytest \
    tests/unit/test_teardown.py::test_sync_close_preserves_independent_failures_in_lifo_order \
    tests/unit/test_teardown.py::test_async_scope_preserves_sync_async_and_generator_failures_in_lifo_order -q
E   RuntimeError: str failed
E   RuntimeError: async failed
2 failed in 0.37s
EXIT=1
```

The raw `str failed` and `async failed` exceptions show that the sabotaged
drains stopped before producing the expected `ExceptionGroup`; the later
finalizers were not attempted. Restoring failure collection produced:

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

The sabotage removed `with self._mutex` from `ScopeFrame.start_flight` while
leaving the same check-then-create body in place. The injected rendezvous table
forces every thread between the lookup and write when the mutex is absent.

```console
$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t uv run --no-sync \
    --python /tmp/depin-step1-313t/bin/python pytest \
    tests/unit/test_free_threading.py::test_the_unified_flight_table_survives_concurrent_creation -q
E   assert all(flight is handed_out[0][0] for flight, _ in handed_out)
1 failed in 1.23s
EXIT=1

$ UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t uv run --no-sync \
    --python /tmp/depin-step1-314t/bin/python pytest \
    tests/unit/test_free_threading.py::test_the_unified_flight_table_survives_concurrent_creation -q
E   assert all(flight is handed_out[0][0] for flight, _ in handed_out)
1 failed in 1.17s
EXIT=1
```

After restoring the mutex, the same commands passed in 1.15s on 3.13t and
1.10s on 3.14t, both with `EXIT=0`.

## Cross-event-loop singleton root cause

The scenario starts 32 OS threads. Every thread owns an `asyncio.run()` event
loop and resolves the same async singleton. Events and a condition make one
leader suspend inside the provider while all followers join the active flight;
there are no timed sleeps.

Against `origin/main` at `4a241d29b51b1582608f4ac356c756d797940ec1`,
the test module from the measured commit was placed on `PYTHONPATH` after the
old source and its standalone worker was invoked with each free-threaded
interpreter:

```console
$ PYTHONPATH=/tmp/depin-step1-old:/tmp/depin-step1-sabotage/tests/unit \
    /tmp/depin-step1-313t/bin/python -c \
    "import multiprocessing, test_free_threading; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=test_free_threading._run_cross_loop_singleton,args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready',ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit',process.exitcode,'alive',process.is_alive()); parent.close()"
pipe_ready True
failure:RuntimeError('<asyncio.locks.Lock object at 0x4b5ea190190 [locked, waiters:1]> is bound to a different event loop')
process_exit 0 alive False

$ PYTHONPATH=/tmp/depin-step1-old:/tmp/depin-step1-sabotage/tests/unit \
    /tmp/depin-step1-314t/bin/python -c \
    "import multiprocessing, test_free_threading; ctx=multiprocessing.get_context('spawn'); parent, child=ctx.Pipe(duplex=False); process=ctx.Process(target=test_free_threading._run_cross_loop_singleton,args=(child,)); process.start(); child.close(); ready=parent.poll(35); print('pipe_ready',ready); result=parent.recv_bytes().decode() if ready else 'no-result'; process.join(35); print(result); print('process_exit',process.exitcode,'alive',process.is_alive()); parent.close()"
pipe_ready True
failure:RuntimeError('<asyncio.locks.Lock object at 0x36356330190 [locked, waiters:1]> is bound to a different event loop')
process_exit 0 alive False
```

The same worker against the measured source returned this on both interpreters:

```text
pipe_ready True
success:constructed=1 resolved=32 identities=1 failures=0
process_exit 0 alive False
```

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
1252/1252  1217 killed  0 timeout  0 suspicious  35 survived  0 skipped  0 no_tests
7.92 mutations/second
EXIT=0
$ uv run mutmut export-cicd-stats
Saved CI/CD stats to mutants/mutmut-cicd-stats.json
EXIT=0
$ uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
mutation score: 97.2% (1217 killed, 35 survived, 1252 total)
EXIT=0
```

The 35 survivors are 2.8% of decided mutants. Every exported inconclusive
field is zero. The mutation-only two-second pytest watchdog turns a deadlock
into a killed test rather than allowing mutmut to classify it as a timeout.

## Per-interpreter coverage

The free-threaded environments contained only the `threads` dependency group;
the three GIL builds used complete isolated development environments. Coverage
was measured independently rather than combined.

| Interpreter | GIL | Command | Tests | `TOTAL` | Coverage | Exit |
| --- | --- | --- | --- | --- | ---: | ---: |
| CPython 3.12.13 | API unavailable | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-final-3.12 uv run --no-sync --python /home/dreco/.local/bin/python3.12 pytest --cov=depin --cov-report=term` | 421 passed, 6 skipped | `1215 9 392 18` | 98.32% | 0 |
| CPython 3.13.13 | enabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-final-3.13 uv run --no-sync --python /home/dreco/.local/bin/python3.13 pytest --cov=depin --cov-report=term` | 421 passed, 6 skipped | `1215 9 392 18` | 98.32% | 0 |
| CPython 3.14.5 | enabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-final-3.14 uv run --no-sync --python /home/dreco/.local/bin/python3.14 pytest --cov=depin --cov-report=term` | 421 passed, 6 skipped | `1181 9 392 18` | 98.28% | 0 |
| CPython 3.13.13 experimental free-threading | disabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-313t uv run --no-sync --python /tmp/depin-step1-313t/bin/python pytest tests/unit --cov=depin --cov-report=term` | 375 passed, 0 skipped | `1215 41 392 17` | 96.02% | 0 |
| CPython 3.14.5 free-threading | disabled | `UV_PROJECT_ENVIRONMENT=/tmp/depin-step1-314t uv run --no-sync --python /tmp/depin-step1-314t/bin/python pytest tests/unit --cov=depin --cov-report=term` | 375 passed, 0 skipped | `1181 41 392 17` | 95.93% | 0 |

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
