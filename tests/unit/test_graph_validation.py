"""Graph validation performed by freeze(): duplicates, cycles, captives, async reach."""

import sys
from collections.abc import AsyncGenerator
from types import ModuleType
from typing import Annotated, override

import pytest

from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.markers import Named, Token, provides
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin.errors import (
    AsyncInSyncContextError,
    CaptiveDependencyError,
    CircularDependencyError,
    DuplicateProviderError,
    MissingProviderError,
)


class MissingProviderSuggestionTarget:
    """Undecorated key looked up by `test_missing_provider_suggests_candidates_with_provides`."""


@provides(MissingProviderSuggestionTarget)
class MissingProviderSuggestionCandidate(MissingProviderSuggestionTarget):
    """The `@provides` class the suggestion scan is expected to find.

    Module-level by necessity: `_suggest_candidates` finds classes by walking
    `sys.modules`, so a function-local class is invisible to it, and no real
    application decorates a function-local class with `@provides` either.
    """


def test_missing_provider_raises() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError, match='A'):
        _ = build_plan(r.records())


def test_default_value_satisfies_missing() -> None:
    class B:
        def __init__(self, x: int = 5) -> None:
            self.x = x

    r = Registry().bind(B, scope=Scope.SINGLETON)
    plan = build_plan(r.records())
    assert len(plan.order) == 1


def test_cycle_detected() -> None:
    class A:
        def __init__(self, b: 'B') -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(A, scope=Scope.SINGLETON).bind(B, scope=Scope.SINGLETON)
    with pytest.raises(CircularDependencyError) as exc:
        _ = build_plan(r.records())
    assert 'A' in str(exc.value)
    assert 'B' in str(exc.value)


def test_reports_all_missing_providers_at_once() -> None:
    class A: ...

    class B: ...

    class Service:
        def __init__(self, a: A, b: B) -> None: ...

    r = Registry().bind(Service, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'A' in msg
    assert 'B' in msg
    assert '2 missing providers' in msg


def test_single_missing_provider_keeps_concise_message() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'missing providers' not in msg
    assert msg.startswith('no provider for ')


def test_defaulted_parameter_is_skipped_while_reporting_another_missing_one() -> None:
    class A: ...

    class B:
        def __init__(self, a: A, x: int = 5) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'missing providers' not in msg
    assert 'int' not in msg


def test_a_cycle_does_not_stop_the_missing_provider_report() -> None:
    class Gone: ...

    class A:
        def __init__(self, b: 'B') -> None: ...

    class B:
        def __init__(self, a: A, gone: Gone) -> None: ...

    r = Registry().bind(A, scope=Scope.SINGLETON).bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError, match='Gone'):
        _ = build_plan(r.records())


def test_the_same_missing_key_is_reported_once_for_equally_deep_chains() -> None:
    class Gone: ...

    class Left:
        def __init__(self, gone: Gone) -> None: ...

    class Right:
        def __init__(self, gone: Gone) -> None: ...

    r = Registry().bind(Left, scope=Scope.SINGLETON).bind(Right, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'missing providers' not in msg
    assert 'Left' in msg
    assert 'Right' not in msg


def test_missing_provider_message_includes_chain() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    class C:
        def __init__(self, b: B) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON).bind(C, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'A' in msg
    assert 'B' in msg
    assert 'C' in msg


def test_missing_provider_suggests_candidates_with_provides() -> None:
    class Repo:
        def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

    r = Registry().bind(Repo, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    assert 'MissingProviderSuggestionCandidate' in str(exc.value)


def test_missing_provider_suggestion_scan_survives_a_hostile_module_attribute() -> None:
    """A module whose attribute access raises must not corrupt the raised error.

    Reproduces the module `__getattr__` hook / lazy-import-shim / partially
    initialised circular import case the scan guards against: reading the
    module's `boom` attribute raises, and the scan must swallow only that,
    still finding the real candidate from another module.
    """

    class _HostileModule(ModuleType):
        @override
        def __getattribute__(self, name: str) -> object:
            if name == 'boom':
                raise RuntimeError('this module attribute always raises')
            return super().__getattribute__(name)

    hostile = _HostileModule('depin_test_hostile_module')
    hostile.__dict__['boom'] = 'trap'
    sys.modules[hostile.__name__] = hostile
    try:

        class Repo:
            def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

        r = Registry().bind(Repo, scope=Scope.SINGLETON)
        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(r.records())
        assert 'MissingProviderSuggestionCandidate' in str(exc.value)
    finally:
        del sys.modules[hostile.__name__]


def test_missing_provider_suggestion_scan_survives_a_hostile_metaclass_getattr() -> None:
    """A class whose metaclass raises on attribute access must not corrupt the raised error.

    `get_provides` reads `__depin_provides__` via `getattr(cls, ..., None)`, whose
    three-argument form suppresses only `AttributeError`. A metaclass `__getattr__`
    raising anything else must still be swallowed by the scan's guard, the same as
    a hostile module attribute is, leaving the real candidate reachable.
    """

    class _HostileMeta(type):
        def __getattr__(cls, name: str) -> object:
            raise RuntimeError('this class attribute always raises')

    class _Hostile(metaclass=_HostileMeta): ...

    hostile_module = ModuleType('depin_test_hostile_metaclass_module')
    hostile_module.__dict__['Hostile'] = _Hostile
    sys.modules[hostile_module.__name__] = hostile_module
    try:

        class Repo:
            def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

        r = Registry().bind(Repo, scope=Scope.SINGLETON)
        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(r.records())
        assert 'MissingProviderSuggestionCandidate' in str(exc.value)
    finally:
        del sys.modules[hostile_module.__name__]


def test_missing_provider_suggestion_scan_survives_a_none_module_entry() -> None:
    """`sys.modules` can hold `None` for a name whose import failed partway.

    The scan guards ``isinstance(module, ModuleType)`` before walking a module's
    namespace; a `None` entry must be skipped rather than raising, and the walk
    must still find the real candidate afterwards. On Python 3.13+, nothing in
    a default interpreter's `sys.modules` exercises this branch any more —
    `typing.io`/`typing.re`, the only non-module entries on 3.12, were removed
    — so this is the only thing that still covers it there.
    """
    name = 'depin_test_none_module_entry'
    assert name not in sys.modules
    # sys.modules can hold None for a failed import; both stubs promise ModuleType.
    sys.modules[name] = None  # type: ignore[assignment]  # pyright: ignore[reportArgumentType]
    try:

        class Repo:
            def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

        r = Registry().bind(Repo, scope=Scope.SINGLETON)
        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(r.records())
        assert 'MissingProviderSuggestionCandidate' in str(exc.value)
    finally:
        del sys.modules[name]


def test_missing_provider_suggestion_does_not_repeat_a_shared_qualname() -> None:
    """Two distinct classes sharing a module and qualname must not repeat in the message.

    Dedup keyed on `id(obj)` lets two distinct `@provides` classes that happen to
    share `__module__` and `__qualname__` — a module reload, or a class factory —
    both pass the check and both emit the same string, visibly duplicated in the
    error. Dedup must instead key on the emitted string.
    """

    class DuplicateQualnameTarget: ...

    def make_candidate() -> type:
        @provides(DuplicateQualnameTarget)
        class Same(DuplicateQualnameTarget): ...

        Same.__qualname__ = 'DuplicateQualnameCandidate'
        return Same

    dup_module = ModuleType('depin_test_duplicate_qualname_module')
    dup_module.__dict__['First'] = make_candidate()
    dup_module.__dict__['Second'] = make_candidate()
    sys.modules[dup_module.__name__] = dup_module
    try:

        class Repo:
            def __init__(self, db: DuplicateQualnameTarget) -> None: ...

        r = Registry().bind(Repo, scope=Scope.SINGLETON)
        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(r.records())
        msg = str(exc.value)
        assert msg.count('DuplicateQualnameCandidate') == 1
    finally:
        del sys.modules[dup_module.__name__]


def test_duplicate_class_binding_raises() -> None:
    class Foo: ...

    r = Registry().bind(Foo, scope=Scope.SINGLETON).bind(Foo, scope=Scope.SINGLETON)
    with pytest.raises(DuplicateProviderError, match='Foo'):
        _ = build_plan(r.records())


def test_duplicate_provides_without_tag_raises() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface).bind(B, provides=Iface)
    with pytest.raises(DuplicateProviderError, match='Iface'):
        _ = build_plan(r.records())


def test_duplicate_value_binding_raises() -> None:
    tok = Token[int]('x')
    r = Registry().value(tok, 100).value(tok, 200)
    with pytest.raises(DuplicateProviderError):
        _ = build_plan(r.records())


def test_same_key_distinct_tags_allowed() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface, tag='a').bind(B, provides=Iface, tag='b')
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_duplicate_message_names_key_and_tag() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface, tag='primary').bind(B, provides=Iface, tag='primary')
    with pytest.raises(DuplicateProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'Iface' in msg
    assert 'primary' in msg
    assert 'two bindings resolve to the same key' in msg
    assert 'distinct tags to register multiple implementations' in msg


def test_multiple_missing_providers_are_deepest_first_and_keep_parameter_names() -> None:
    class DeepMissing: ...

    class ShallowMissing: ...

    class Leaf:
        def __init__(self, dependency: DeepMissing) -> None: ...

    class Root:
        def __init__(self, leaf: Leaf, shallow: ShallowMissing) -> None: ...

    registry = Registry().bind(Leaf).bind(Root)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(registry.records())
    message = str(exc.value)
    assert message.startswith('2 missing providers:\n  - ')
    assert message.index('DeepMissing') < message.index('ShallowMissing')
    assert '.Leaf.dependency' in message
    assert '.Root -> ' in message
    assert '.Leaf -> ' in message


def test_missing_scan_continues_after_a_defaulted_parameter() -> None:
    class Missing: ...

    class Service:
        def __init__(self, defaulted: int = 1, *, required: Missing) -> None: ...

    registry = Registry().bind(Service)
    with pytest.raises(MissingProviderError, match='Missing'):
        _ = build_plan(registry.records())


def test_singleton_depending_on_scoped_is_rejected() -> None:
    class Session: ...

    class Service:
        def __init__(self, session: Session) -> None: ...

    r = Registry().bind(Session, scope=Scope.SCOPED).bind(Service, scope=Scope.SINGLETON)
    with pytest.raises(CaptiveDependencyError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'Service' in msg
    assert 'Session' in msg


def test_singleton_capturing_scoped_through_transient_is_rejected() -> None:
    class Session: ...

    class Work:
        def __init__(self, session: Session) -> None: ...

    class Service:
        def __init__(self, work: Work) -> None: ...

    r = (
        Registry()
        .bind(Session, scope=Scope.SCOPED)
        .bind(Work, scope=Scope.TRANSIENT)
        .bind(Service, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError) as exc:
        _ = build_plan(r.records())
    chain = str(exc.value).split('chain: ', 1)[1]
    assert chain.index('Service') < chain.index('Work') < chain.index('Session')


def test_captive_chain_names_the_branch_the_walk_took() -> None:
    class Session: ...

    class Inner:
        def __init__(self, session: Session) -> None: ...

    class Left:
        def __init__(self, inner: Inner) -> None: ...

    class Right:
        def __init__(self, inner: Inner) -> None: ...

    class Service:
        def __init__(self, left: Left, right: Right) -> None: ...

    r = (
        Registry()
        .bind(Session, scope=Scope.SCOPED)
        .bind(Inner, scope=Scope.TRANSIENT)
        .bind(Left, scope=Scope.TRANSIENT)
        .bind(Right, scope=Scope.TRANSIENT)
        .bind(Service, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError) as exc:
        _ = build_plan(r.records())
    chain = str(exc.value).split('chain: ', 1)[1].split(')', 1)[0]
    assert [step.rsplit('.', 1)[-1] for step in chain.split(' -> ')] == ['Service', 'Right', 'Inner', 'Session']


def test_scoped_depending_on_scoped_is_allowed() -> None:
    class Session: ...

    class Repo:
        def __init__(self, session: Session) -> None: ...

    r = Registry().bind(Session, scope=Scope.SCOPED).bind(Repo, scope=Scope.SCOPED)
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_singleton_depending_on_transient_is_allowed() -> None:
    class Clock: ...

    class Service:
        def __init__(self, clock: Clock) -> None: ...

    r = Registry().bind(Clock, scope=Scope.TRANSIENT).bind(Service, scope=Scope.SINGLETON)
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_singleton_transient_diamond_is_allowed() -> None:
    class Leaf: ...

    class Left:
        def __init__(self, leaf: Leaf) -> None: ...

    class Right:
        def __init__(self, leaf: Leaf) -> None: ...

    class Service:
        def __init__(self, left: Left, right: Right) -> None: ...

    r = (
        Registry()
        .bind(Leaf, scope=Scope.TRANSIENT)
        .bind(Left, scope=Scope.TRANSIENT)
        .bind(Right, scope=Scope.TRANSIENT)
        .bind(Service, scope=Scope.SINGLETON)
    )
    plan = build_plan(r.records())
    assert len(plan.order) == 4


def test_sync_chain_with_async_dep_rejected() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    class B:
        def __init__(self, a: A) -> None: ...

    def sync_use(b: B) -> int:
        return 0

    r = (
        Registry()
        .bind(make_a, scope=Scope.SINGLETON, provides=A)
        .bind(B, scope=Scope.SINGLETON)
        .bind(sync_use, scope=Scope.SINGLETON)
    )
    plan = build_plan(r.records())
    sync_spec = next(s for s in plan.order if s.source is sync_use)
    assert sync_spec.needs_async is True


def test_async_dependency_propagates_through_a_sync_chain() -> None:
    async def make_a() -> int:
        return 1

    def make_b(a: int) -> str:
        return str(a)

    def make_c(b: str) -> bytes:
        return b.encode()

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=int)
        .bind(make_b, scope=Scope.SINGLETON, provides=str)
        .bind(make_c, scope=Scope.SINGLETON, provides=bytes)
        .freeze()
    )
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[bytes]


def test_async_generator_dependency_propagates_to_its_consumer() -> None:
    async def make_a() -> AsyncGenerator[int]:
        yield 1

    def use(a: int) -> str:
        return str(a)

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=int)
        .bind(use, scope=Scope.SINGLETON, provides=str)
        .freeze()
    )
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[str]


def test_a_string_key_referenced_by_named_must_still_be_bound() -> None:
    def provider() -> int:
        return 99

    def consumer(x: Annotated[int, Named('legacy_key')]) -> str:
        return str(x)

    builder = (
        Container()
        .bind(provider, scope=Scope.SINGLETON, provides=int)
        .bind(consumer, scope=Scope.SINGLETON, provides=str)
    )
    with pytest.raises(MissingProviderError, match='legacy_key'):
        _ = builder.freeze()
