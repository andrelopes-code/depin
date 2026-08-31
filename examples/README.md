# Examples

Every example is a runnable module and is executed by
`tests/integration/test_examples.py`, so none of them can drift from the library.

| Example | Run | Shows |
| --- | --- | --- |
| [`minimal_sync`](minimal_sync/main.py) | `python -m examples.minimal_sync.main` | Tokens, a factory that owns a resource, and `close()`. |
| [`scopes`](scopes/main.py) | `python -m examples.scopes.main` | Singleton vs scoped lifetimes, teardown on scope exit, nested scopes. |
| [`testing`](testing/main.py) | `python -m examples.testing.main` | `@provides` against a `Protocol`, and `override()` as a test seam. |
| [`aliasing`](aliasing/main.py) | `python -m examples.aliasing.main` | `alias()` giving one instance two names, and `explain()` on the result. |
| [`optional_dependencies`](optional_dependencies/main.py) | `python -m examples.optional_dependencies.main` | A `T \| None` parameter resolving to `None` or to the bound instance. |
| [`collections`](collections/main.py) | `python -m examples.collections.main` | `collect()` gathering several handlers behind `list[Handler]`, and `explain()` on the collection. |
| [`decoration`](decoration/main.py) | `python -m examples.decoration.main` | `decorate()` stacking a caching and a logging wrapper over one binding, and `explain()` on the chain. |
| [`conditional`](conditional/main.py) | `python -m examples.conditional.main` | `when=` choosing between two implementations of one key, a binding switched off entirely, and `explain()` on the inactive note. |
| [`generic_keys`](generic_keys/main.py) | `python -m examples.generic_keys.main` | `Repo[User]` and `Repo[Order]` as two provider keys, a service depending on both, and `explain()` on one parameterisation. |
| [`graph_diagnostics`](graph_diagnostics/main.py) | `python -m examples.graph_diagnostics.main` | `explain()` for one key, and the `mermaid` export of the whole graph. |
| [`warmup`](warmup/main.py) | `python -m examples.warmup.main` | `warmup()` building every singleton in one pass, and a scoped provider it leaves alone. |
| [`health`](health/main.py) | `python -m examples.health.main` | `bind(..., check=...)` declaring a check, `checks()` describing it, and `health()` reporting a passing and a failing one. |
| [`fastapi_app`](fastapi_app/main.py) | `uvicorn examples.fastapi_app.main:create_app --factory` | Registries, an app factory, one scope per request, `aclose()` on shutdown. |

Install the extras first:

```bash
uv sync --all-extras
```
