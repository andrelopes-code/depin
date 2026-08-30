"""The scope frame: value chaining, scope_value bindings, and frame lifetime."""

import asyncio
import threading

import pytest

from depin._core.container import Container
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, push_frame
from depin.errors import MissingProviderError, OutsideScopeError


async def _checkpoint() -> None:
    loop = asyncio.get_running_loop()
    checkpoint = loop.create_future()
    loop.call_soon(checkpoint.set_result, None)
    await checkpoint


def test_active_frame_raises_without_push() -> None:
    with pytest.raises(OutsideScopeError):
        _ = active_frame()


@pytest.mark.asyncio
async def test_finishing_flight_completes_registered_async_waiter() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight, joins = frame.start_flight(key)
    assert not joins

    waiter = asyncio.create_task(frame.wait_async(flight))
    checkpoint = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(checkpoint.set_result, None)
    await checkpoint

    frame.finish_flight(key, leader)
    await asyncio.wait_for(waiter, timeout=1)


@pytest.mark.asyncio
async def test_publish_makes_value_visible_before_followers_are_signalled() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight, joins = frame.start_flight(key)
    assert not joins

    waiter = asyncio.create_task(frame.wait_async(flight))
    await _checkpoint()
    follower = frame.publish(key, leader, 'value')

    assert frame.lookup(key) == 'value'
    assert follower is flight
    assert not waiter.done()

    assert follower is not None
    follower.finish()
    await asyncio.wait_for(waiter, timeout=1)


@pytest.mark.asyncio
async def test_abort_wakes_all_followers_and_allows_one_replacement_leader() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight_one, joins = frame.start_flight(key)
    assert not joins
    flight_two, joins = frame.start_flight(key)
    assert not joins
    waiter_one = asyncio.create_task(frame.wait_async(flight_one))
    waiter_two = asyncio.create_task(frame.wait_async(flight_two))
    await _checkpoint()

    followers = frame.abort(key, leader)
    assert followers is flight_one
    assert followers is not None
    followers.finish()
    await asyncio.wait_for(asyncio.gather(waiter_one, waiter_two), timeout=1)

    replacement, replacement_leader = frame.start_flight(key)
    assert replacement_leader
    follower, follower_leader = frame.start_flight(key)
    assert not follower_leader
    signalled = frame.publish(key, replacement, 'replacement')
    assert signalled is follower
    assert signalled is not None
    signalled.finish()
    assert frame.lookup(key) == 'replacement'


@pytest.mark.asyncio
async def test_cancelling_one_async_follower_leaves_another_waiter_live() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight, joins = frame.start_flight(key)
    assert not joins
    cancelled = asyncio.create_task(frame.wait_async(flight))
    live = asyncio.create_task(frame.wait_async(flight))
    await _checkpoint()

    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert not live.done()

    frame.finish_flight(key, leader)
    await asyncio.wait_for(live, timeout=1)


@pytest.mark.asyncio
async def test_stale_publish_cannot_cache_or_signal_a_replacement_flight() -> None:
    frame = ScopeFrame()
    key = object()
    old, constructs = frame.start_flight(key)
    assert constructs
    old_follower, joins = frame.start_flight(key)
    assert not joins
    abandoned = frame.abort(key, old)
    assert abandoned is old_follower
    assert abandoned is not None
    abandoned.finish()

    replacement, replacement_leader = frame.start_flight(key)
    assert replacement_leader
    replacement_follower, joins = frame.start_flight(key)
    assert not joins
    assert frame.publish(key, old, 'stale') is None
    assert frame.lookup(key) is MISSING
    assert not replacement.finished

    signalled = frame.publish(key, replacement, 'valid')
    assert signalled is replacement_follower
    assert frame.lookup(key) == 'valid'
    assert not replacement.finished
    assert signalled is not None
    signalled.finish()
    await frame.wait_async(replacement_follower)


@pytest.mark.asyncio
async def test_flight_completion_resumes_waiter_on_its_owning_loop_and_thread() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight, joins = frame.start_flight(key)
    assert not joins
    owner_loop = asyncio.get_running_loop()
    owner_thread = threading.get_ident()
    resumed: list[tuple[asyncio.AbstractEventLoop, int]] = []

    async def wait_for_flight() -> None:
        await frame.wait_async(flight)
        resumed.append((asyncio.get_running_loop(), threading.get_ident()))

    waiter = asyncio.create_task(wait_for_flight())
    await _checkpoint()

    finished = threading.Event()

    def finish_from_other_thread() -> None:
        frame.finish_flight(key, leader)
        finished.set()

    finisher = threading.Thread(target=finish_from_other_thread)
    finisher.start()
    assert finished.wait(1)
    finisher.join()
    await asyncio.wait_for(waiter, timeout=1)

    assert resumed == [(owner_loop, owner_thread)]


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


def test_start_flight_designates_one_leader_and_joins_followers() -> None:
    frame = ScopeFrame()
    key = object()

    first, first_constructs = frame.start_flight(key)
    second, second_constructs = frame.start_flight(key)

    assert first_constructs
    assert second is not first
    assert not second_constructs


def test_child_frame_joins_an_ancestor_construction_flight() -> None:
    parent = ScopeFrame()
    child = ScopeFrame(parent)
    key = object()

    cached, leader = parent.claim_cached(key)
    child_cached, follower = child.claim_cached(key)

    assert cached is MISSING
    assert parent.is_leader(leader)
    assert child_cached is MISSING
    assert not child.is_leader(follower)


def test_child_claim_returns_cached_value_from_ancestor() -> None:
    parent = ScopeFrame()
    child = ScopeFrame(parent)
    key = object()
    parent.provide(key, 'ancestor-value')

    value, flight = child.claim_cached(key)

    assert value == 'ancestor-value'
    assert flight is None


def test_child_claim_creates_leader_when_no_visible_cache_or_flight_exists() -> None:
    parent = ScopeFrame()
    child = ScopeFrame(parent)
    key = object()

    value, flight = child.claim_cached(key)

    assert value is MISSING
    assert flight is not None
    assert child.is_leader(flight)


def test_second_child_joins_shared_flight_materialized_in_ancestor() -> None:
    parent = ScopeFrame()
    first_child = ScopeFrame(parent)
    second_child = ScopeFrame(parent)
    key = object()
    leader, constructs = parent.start_flight(key)
    assert constructs

    first_value, first_flight = first_child.claim_cached(key)
    second_value, second_flight = second_child.claim_cached(key)

    assert first_value is MISSING
    assert second_value is MISSING
    assert first_flight is second_flight
    assert not first_child.is_leader(first_flight)
    parent.finish_flight(key, leader)


def test_start_flight_raises_for_cached_key() -> None:
    frame = ScopeFrame()
    key = object()
    frame.provide(key, 'cached')

    with pytest.raises(KeyError):
        frame.start_flight(key)


def test_finishing_a_flight_twice_is_idempotent() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    follower, joins = frame.start_flight(key)
    assert not joins
    signalled = frame.publish(key, leader, 'value')
    assert signalled is follower
    assert signalled is not None

    signalled.finish()
    signalled.finish()

    assert signalled.finished


@pytest.mark.asyncio
async def test_non_flight_waits_and_non_leader_finish_are_noops() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    follower, joins = frame.start_flight(key)
    assert not joins

    frame.wait_sync(leader)
    await frame.wait_async(leader)
    frame.finish_flight(key, follower)

    assert not follower.finished
    signalled = frame.publish(key, leader, 'value')
    assert signalled is follower
    assert signalled is not None
    signalled.finish()


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
