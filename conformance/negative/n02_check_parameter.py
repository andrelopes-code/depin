"""`check=` given a function whose parameter is not the bound type.

`bind` infers the check's parameter from the same `T` the binding provides, so a
check written against another class cannot be attached to it.

This fixture is `tests/typing/test_conformance.py:304` moved out of the
repository's own gate. There it was written as
``# type: ignore[arg-type]  # pyright: ignore[reportArgumentType]``, a spelling
that fails a five-checker world twice over: ty honours neither half, and mypy's
``warn_unused_ignores`` — implied by ``strict`` — turns the assertion into a
gate failure the moment any checker stops reporting the error it guards. The
expected diagnostic is data here, in `expected/negative.toml`, so nothing in
this file tells a checker what to say and nothing in it silences one.
"""

from depin import Container


class Database: ...


class Cache: ...


def ping(cache: Cache) -> None:
    _ = cache


def main() -> None:
    _ = Container().bind(Database, check=ping)
