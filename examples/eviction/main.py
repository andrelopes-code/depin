"""Evicting a singleton consumer's cache around an override.

The pattern the `depin.ext.pytest` plugin's `depin_override` fixture
automates. Run with ``python -m examples.eviction.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer, provides


class Clock(Protocol):
    def now(self) -> str: ...


@provides(Clock)
class SystemClock:
    def now(self) -> str:
        return 'real-time'


class FakeClock:
    def now(self) -> str:
        return 'fake-time'


class Report:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def render(self) -> str:
        return f'report at {self.clock.now()}'


def build() -> FrozenContainer:
    return Container().bind(SystemClock).bind(Report).freeze()


def main() -> None:
    di = build()

    print(di[Clock].now())
    print(di[Report].render())

    with di.override(Clock).using(FakeClock()):
        # The overridden key is replaced immediately, even for a singleton
        # already built above.
        print(di[Clock].now())

        # Report was already built and cached with the real Clock; it keeps
        # it, because override() replaces the key, not every value already
        # constructed from it.
        print(di[Report].render())

        # reset() drops every built singleton's cache, so the next
        # resolution of Report rebuilds it and sees the override that is
        # active right now.
        di.reset()
        print(di[Report].render())

    # Outside the block the override is gone; reset() again so the next
    # resolution rebuilds Report against the real Clock.
    di.reset()
    print(di[Report].render())


if __name__ == '__main__':
    main()
