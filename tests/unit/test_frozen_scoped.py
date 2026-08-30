import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import MissingProviderError, OutsideScopeError


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
    with pytest.raises(
        OutsideScopeError,
        match=r'^no active scope frame; open one with FrozenContainer\.scope\(\) or \.ascope\(\)$',
    ):
        _ = frozen[A]


def test_missing_scope_value_names_the_key_and_how_to_provide_it() -> None:
    class Request: ...

    frozen = Container().scope_value(Request).freeze()
    with (
        frozen.scope(),
        pytest.raises(
            MissingProviderError,
            match=(
                r'^no value in the active scope for .*Request; '
                r'a key declared with scope_value\(\) must be supplied by whoever opens the scope, '
                r'with frame\.provide\(key, value\)$'
            ),
        ),
    ):
        _ = frozen[Request]
