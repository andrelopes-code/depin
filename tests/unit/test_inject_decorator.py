import pytest

from depin._core.container import Container
from depin._core.scope import Scope


def test_inject_fills_typed_params() -> None:
    class Service:
        def __init__(self) -> None:
            self.value = 7

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(svc: Service, multiplier: int) -> int:
        return svc.value * multiplier

    # Python's typing cannot express "after @inject these params become optional".
    assert handler(multiplier=2) == 14  # pyright: ignore[reportCallIssue]


def test_inject_does_not_override_explicit_args() -> None:
    class Service:
        def __init__(self) -> None:
            self.v = 1

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(svc: Service) -> int:
        return svc.v

    other = Service()
    other.v = 99
    assert handler(svc=other) == 99


@pytest.mark.asyncio
async def test_inject_async() -> None:
    async def dep() -> int:
        return 21

    frozen = Container().bind(dep, scope=Scope.TRANSIENT, provides=int).freeze()

    @frozen.inject
    async def handler(n: int) -> int:
        return n * 2

    # Python's typing cannot express "after @inject these params become optional".
    assert await handler() == 42  # pyright: ignore[reportCallIssue]
