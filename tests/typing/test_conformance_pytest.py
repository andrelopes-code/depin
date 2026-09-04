"""Static conformance of `depin.ext.pytest`'s fixture factories under both type checkers.

Each factory is exercised inside a nested function that is defined but never
called: the outer `test_...` function takes no fixture parameters itself, so
pytest runs it as an ordinary, instant test, while `assert_type` inside the
nested function is still checked statically by both `basedpyright` and `mypy`,
neither of which cares whether a function is ever invoked.
"""

from typing import assert_type

from depin import FrozenContainer
from depin.ext.pytest import AsyncOverrideFactory, OverrideFactory


class Clock:
    def now(self) -> str:
        return 'real'


class FakeClock:
    def now(self) -> str:
        return 'fake'


def test_override_factory_yields_the_container() -> None:
    def consumer(depin_override: OverrideFactory) -> None:
        with depin_override(Clock).using(FakeClock()) as di:
            assert_type(di, FrozenContainer)

    _ = consumer


def test_async_override_factory_yields_the_container() -> None:
    def consumer(depin_aoverride: AsyncOverrideFactory) -> None:
        async def use() -> None:
            async with depin_aoverride(Clock).using(FakeClock()) as di:
                assert_type(di, FrozenContainer)

        _ = use

    _ = consumer
