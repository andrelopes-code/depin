# Examples

Every example is a runnable module and is executed by
`tests/integration/test_examples.py`, so none of them can drift from the library.

| Example | Run | Shows |
| --- | --- | --- |
| [`minimal_sync`](minimal_sync/main.py) | `python -m examples.minimal_sync.main` | Tokens, a factory that owns a resource, and `close()`. |
| [`scopes`](scopes/main.py) | `python -m examples.scopes.main` | Singleton vs scoped lifetimes, teardown on scope exit, nested scopes. |
| [`testing`](testing/main.py) | `python -m examples.testing.main` | `@provides` against a `Protocol`, and `override()` as a test seam. |
| [`graph_diagnostics`](graph_diagnostics/main.py) | `python -m examples.graph_diagnostics.main` | `explain()` for one key, and the `mermaid` export of the whole graph. |
| [`fastapi_app`](fastapi_app/main.py) | `uvicorn examples.fastapi_app.main:create_app --factory` | Registries, an app factory, one scope per request, `aclose()` on shutdown. |

Install the extras first:

```bash
uv sync --all-extras
```
