import pytest

from depin._core.scope import ScopeFrame, active_frame, push_frame
from depin.errors import OutsideScopeError


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
        f.put('k', 1)
        assert f.get('k') == 1


def test_frame_get_walks_parents() -> None:
    with push_frame() as outer:
        outer.put('k', 'outer-value')
        with push_frame() as inner:
            assert inner.get('k') == 'outer-value'


def test_frame_contains_walks_parents() -> None:
    with push_frame() as outer:
        outer.put('k', 1)
        with push_frame() as inner:
            assert 'k' in inner
            assert 'missing' not in inner


def test_frame_get_raises_keyerror() -> None:
    with push_frame() as f, pytest.raises(KeyError):
        _ = f.get('missing')
