"""Replacing a dependency in a test without rebuilding the container.

Run with ``python -m examples.testing.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer, Scope, provides


class Clock(Protocol):
    def now(self) -> str: ...


@provides(Clock)  # type: ignore[type-abstract]  # mypy treats any type[Protocol] as non-instantiable; provides() only stores it
class SystemClock:
    """Bound under `Clock` because of the decorator — no ``provides=`` needed."""

    def now(self) -> str:
        return 'real-time'


class FrozenClock:
    def __init__(self, stamp: str) -> None:
        self._stamp = stamp

    def now(self) -> str:
        return self._stamp


class Report:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def render(self) -> str:
        return f'report at {self.clock.now()}'


def build() -> FrozenContainer:
    return Container().bind(SystemClock).bind(Report, scope=Scope.TRANSIENT).freeze()


def main() -> None:
    di = build()

    print(di[Report].render())

    # The override applies everywhere the key appears, including deep in the
    # graph — Report never learns that its Clock was swapped.
    with di.override(Clock, FrozenClock('2026-01-01')):
        print(di[Report].render())

    print(di[Report].render())


if __name__ == '__main__':
    main()
