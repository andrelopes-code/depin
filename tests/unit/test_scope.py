from depin._core.scope import Scope


def test_scope_values() -> None:
    assert Scope.SINGLETON.value == 'singleton'
    assert Scope.SCOPED.value == 'scoped'
    assert Scope.TRANSIENT.value == 'transient'


def test_scope_distinct() -> None:
    assert {Scope.SINGLETON, Scope.SCOPED, Scope.TRANSIENT} == set(Scope)
