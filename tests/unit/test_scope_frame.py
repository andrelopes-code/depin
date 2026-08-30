"""The scope frame: value chaining, scope_value bindings, and frame lifetime."""

import pytest

from depin._core.container import Container
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, push_frame
from depin.errors import MissingProviderError, OutsideScopeError


def test_active_frame_raises_without_push() -> None:
    with pytest.raises(OutsideScopeError):
        _ = active_frame()


def test_push_frame_sets_active() -> None:
    with push_frame() as frame:
        assert isinstance(frame, ScopeFrame)
        assert active_frame() is frame


def test_nested_push_restores_outer() -> None:
    with push_frame() as outer:
        with push_frame() as inner:
            assert active_frame() is inner
            assert inner.parent is outer
        assert active_frame() is outer


def test_frame_caches_objects() -> None:
    with push_frame() as f:
        f.provide('k', 1)
        assert f.get('k') == 1


def test_frame_get_walks_parents() -> None:
    with push_frame() as outer:
        outer.provide('k', 'outer-value')
        with push_frame() as inner:
            assert inner.get('k') == 'outer-value'


def test_frame_contains_walks_parents() -> None:
    with push_frame() as outer:
        outer.provide('k', 1)
        with push_frame() as inner:
            assert 'k' in inner
            assert 'missing' not in inner


def test_frame_get_raises_keyerror() -> None:
    with push_frame() as f, pytest.raises(KeyError) as exc:
        _ = f.get('missing')
    assert exc.value.args == ('missing',)


def test_lookup_reports_absence_without_raising() -> None:
    frame = ScopeFrame()
    assert frame.lookup('nope') is MISSING
    frame.provide('nope', None)
    assert frame.lookup('nope') is None
    assert 'nope' in frame


def test_a_scope_value_must_be_supplied_before_it_resolves() -> None:
    class Marker: ...

    frozen = Container().scope_value(Marker).freeze()
    with frozen.scope(), pytest.raises(MissingProviderError, match='scope_value'):
        _ = frozen[Marker]


def test_a_scope_value_resolves_to_whatever_the_scope_provided() -> None:
    class Marker: ...

    frozen = Container().scope_value(Marker).freeze()
    sentinel = Marker()
    with frozen.scope() as frame:
        frame.provide(Marker, sentinel)
        assert frozen[Marker] is sentinel


def test_a_scope_value_is_injected_into_a_sync_provider() -> None:
    class Report:
        def __init__(self, dep: int) -> None:
            self.dep = dep

    frozen = Container().bind(Report, scope=Scope.SCOPED).scope_value(int).freeze()
    with frozen.scope() as frame:
        frame.provide(int, 13)
        assert frozen[Report].dep == 13


def test_scope_values_do_not_skip_later_bound_dependencies() -> None:
    class ScopeValue: ...

    class BoundValue: ...

    class Report:
        def __init__(self, scope_value: ScopeValue, bound_value: BoundValue) -> None:
            self.scope_value = scope_value
            self.bound_value = bound_value

    frozen = Container().scope_value(ScopeValue).bind(BoundValue).bind(Report, scope=Scope.SCOPED).freeze()
    supplied = ScopeValue()
    with frozen.scope() as frame:
        frame.provide(ScopeValue, supplied)
        report = frozen[Report]

    assert report.scope_value is supplied
    assert isinstance(report.bound_value, BoundValue)


def test_a_scope_value_outside_any_scope_raises() -> None:
    class Marker: ...

    frozen = Container().scope_value(Marker).freeze()
    with pytest.raises(OutsideScopeError):
        _ = frozen[Marker]
