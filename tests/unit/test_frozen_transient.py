from depin._core.container import Container
from depin._core.scope import Scope


def test_transient_returns_fresh_instances() -> None:
    class A:
        def __init__(self) -> None: ...

    frozen = Container().bind(A, scope=Scope.TRANSIENT).freeze()
    assert frozen[A] is not frozen[A]


def test_transient_function_called_per_resolution() -> None:
    calls = {'n': 0}

    def make() -> int:
        calls['n'] += 1
        return calls['n']

    frozen = Container().bind(make, scope=Scope.TRANSIENT, provides=int).freeze()
    assert frozen[int] == 1
    assert frozen[int] == 2
    assert calls['n'] == 2
