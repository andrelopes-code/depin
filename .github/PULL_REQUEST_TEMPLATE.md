## Summary

<!-- What does this change do, and why? Link any related issues. -->

## Checklist

- [ ] The PR title follows Conventional Commits (e.g. `feat:`, `fix:`, `docs:`).
- [ ] `uv run ruff format` passes.
- [ ] `uv run ruff check` passes.
- [ ] `uv run basedpyright` passes.
- [ ] `uv run mypy` passes.
- [ ] `uv run pytest` passes.
- [ ] The typing conformance jobs are green in CI — `typing-artifact`,
      `typing-consumer` and `typing-source`. They build a wheel, so they run in
      CI rather than as a sixth local gate; reproduce a failure locally with
      `uv run python -m scripts.conformance`.
- [ ] Tests added or updated for the change.
- [ ] Coverage for `depin/_core/` holds at or above 95%.
- [ ] Documentation updated if needed.
