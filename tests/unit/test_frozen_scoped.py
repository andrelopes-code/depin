import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import OutsideScopeError


def test_scoped_class_same_within_scope() -> None:
    class A:
        def __init__(self) -> None: ...

    frozen = Container().bind(A, scope=Scope.SCOPED).freeze()
    with frozen.scope():
        a1 = frozen[A]
        a2 = frozen[A]
    assert a1 is a2


def test_scoped_class_distinct_across_scopes() -> None:
    class A:
        def __init__(self) -> None: ...

    frozen = Container().bind(A, scope=Scope.SCOPED).freeze()
    with frozen.scope():
        a1 = frozen[A]
    with frozen.scope():
        a2 = frozen[A]
    assert a1 is not a2


def test_scoped_resolve_without_scope_raises() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SCOPED).freeze()
    with pytest.raises(OutsideScopeError):
        _ = frozen[A]
