"""Graph validation diagnostics and missing-provider suggestions."""

import sys
from types import ModuleType
from typing import override

import pytest

from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.markers import provides
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin.errors import CaptiveDependencyError, CircularDependencyError, MissingProviderError


class MissingProviderSuggestionTarget:
    """Undecorated key used by suggestion scan tests."""


@provides(MissingProviderSuggestionTarget)
class MissingProviderSuggestionCandidate(MissingProviderSuggestionTarget):
    """Candidate found by the suggestion scan."""


class _MissingCycleA:
    def __init__(self, b: '_MissingCycleB') -> None: ...


class _MissingCycleB:
    def __init__(self, a: _MissingCycleA, absent: '_MissingCycleDependency') -> None: ...


class _MissingCycleDependency: ...


def test_cycle_message_preserves_the_arrow_delimiter() -> None:
    class A:
        def __init__(self, b: 'B') -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    with pytest.raises(CircularDependencyError) as exc:
        _ = Container().bind(A).bind(B).freeze()
    chain = str(exc.value).removeprefix('cycle detected: ')
    assert [step.rsplit('.', 1)[-1] for step in chain.split(' -> ')] == ['A', 'B', 'A']


def test_missing_provider_suggests_candidates_with_provides() -> None:
    class Repo:
        def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(Registry().bind(Repo, scope=Scope.SINGLETON).records())
    assert 'MissingProviderSuggestionCandidate' in str(exc.value)


def test_suggestion_scan_continues_after_a_hostile_attribute_in_its_own_module() -> None:
    class _HostileModule(ModuleType):
        @override
        def __getattribute__(self, name: str) -> object:
            if name == 'boom':
                raise RuntimeError('this module attribute always raises')
            return super().__getattribute__(name)

    class Target: ...

    @provides(Target)
    class Candidate(Target): ...

    hostile = _HostileModule('depin_test_hostile_module_with_candidate')
    hostile.__dict__['boom'] = 'trap'
    hostile.__dict__['Candidate'] = Candidate
    sys.modules[hostile.__name__] = hostile
    try:

        class Service:
            def __init__(self, target: Target) -> None: ...

        with pytest.raises(MissingProviderError) as exc:
            _ = Container().bind(Service).freeze()
        assert 'Candidate' in str(exc.value)
    finally:
        del sys.modules[hostile.__name__]


def test_suggestion_scan_skips_non_classes_and_inspects_each_class_once() -> None:
    reads: list[str] = []

    class Target: ...

    class _NonClass:
        @override
        def __getattribute__(self, name: str) -> object:
            if name == '__depin_provides__':
                reads.append('non-class')
            return super().__getattribute__(name)

    class _CountingMeta(type):
        @override
        def __getattribute__(cls, name: str) -> object:
            if name == '__depin_provides__':
                reads.append('candidate')
            return super().__getattribute__(name)

    @provides(Target)
    class Candidate(Target, metaclass=_CountingMeta): ...

    module = ModuleType('depin_test_suggestion_scan_identity')
    module.__dict__['value'] = _NonClass()
    module.__dict__['first_candidate'] = Candidate
    module.__dict__['second_candidate'] = Candidate
    sys.modules[module.__name__] = module
    try:

        class Service:
            def __init__(self, target: Target) -> None: ...

        with pytest.raises(MissingProviderError, match='Candidate'):
            _ = Container().bind(Service).freeze()
        assert reads == ['candidate']
    finally:
        del sys.modules[module.__name__]


def test_suggestion_scan_continues_after_a_hostile_class_in_its_own_module() -> None:
    class Target: ...

    class _HostileMeta(type):
        @override
        def __getattribute__(cls, name: str) -> object:
            if name == '__depin_provides__':
                raise RuntimeError('this class attribute always raises')
            return super().__getattribute__(name)

    class Hostile(metaclass=_HostileMeta): ...

    @provides(Target)
    class Candidate(Target): ...

    module = ModuleType('depin_test_hostile_class_with_candidate')
    module.__dict__['Hostile'] = Hostile
    module.__dict__['Candidate'] = Candidate
    sys.modules[module.__name__] = module
    try:

        class Service:
            def __init__(self, target: Target) -> None: ...

        with pytest.raises(MissingProviderError) as exc:
            _ = Container().bind(Service).freeze()
        assert 'Candidate' in str(exc.value)
    finally:
        del sys.modules[module.__name__]


def test_missing_provider_suggestion_scan_survives_a_none_module_entry() -> None:
    name = 'depin_test_none_module_entry'
    assert name not in sys.modules
    sys.modules[name] = None  # type: ignore[assignment]  # pyright: ignore[reportArgumentType]
    try:

        class Repo:
            def __init__(self, db: MissingProviderSuggestionTarget) -> None: ...

        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(Registry().bind(Repo, scope=Scope.SINGLETON).records())
        assert 'MissingProviderSuggestionCandidate' in str(exc.value)
    finally:
        del sys.modules[name]


def test_missing_provider_suggestion_does_not_repeat_a_shared_qualname() -> None:
    class Target: ...

    def make_candidate() -> type:
        @provides(Target)
        class Same(Target): ...

        Same.__qualname__ = 'DuplicateQualnameCandidate'
        return Same

    module = ModuleType('depin_test_duplicate_qualname_module')
    module.__dict__['First'] = make_candidate()
    module.__dict__['Second'] = make_candidate()
    sys.modules[module.__name__] = module
    try:

        class Repo:
            def __init__(self, db: Target) -> None: ...

        with pytest.raises(MissingProviderError) as exc:
            _ = build_plan(Registry().bind(Repo, scope=Scope.SINGLETON).records())
        assert str(exc.value).count('DuplicateQualnameCandidate') == 1
    finally:
        del sys.modules[module.__name__]


def test_missing_provider_suggestions_are_comma_separated() -> None:
    class Target: ...

    @provides(Target)
    class FirstCandidate(Target): ...

    @provides(Target)
    class SecondCandidate(Target): ...

    suggestions = ModuleType('depin_test_multiple_suggestions')
    suggestions.__dict__['FirstCandidate'] = FirstCandidate
    suggestions.__dict__['SecondCandidate'] = SecondCandidate
    sys.modules[suggestions.__name__] = suggestions
    try:

        class Service:
            def __init__(self, target: Target) -> None: ...

        with pytest.raises(MissingProviderError) as exc:
            _ = Container().bind(Service).freeze()
        message = str(exc.value)
        assert 'FirstCandidate, ' in message
        assert 'FirstCandidate, test_graph_diagnostics.' in message
        assert '.SecondCandidate' in message
    finally:
        del sys.modules[suggestions.__name__]


def test_multiple_missing_provider_lines_keep_the_documented_bullet_separator() -> None:
    class First: ...

    class Second: ...

    class Service:
        def __init__(self, first: First, second: Second) -> None: ...

    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(Registry().bind(Service).records())

    message = str(exc.value)
    first = message.index('.First)')
    second = message.index('no provider for ', first + 1)
    assert message[first:second].endswith('\n  - ')
    assert 'XX\n  - XX' not in message


def test_missing_provider_without_suggestions_has_no_candidates_suffix() -> None:
    class Target: ...

    class Service:
        def __init__(self, target: Target) -> None: ...

    with pytest.raises(MissingProviderError) as exc:
        _ = Container().bind(Service).freeze()
    assert '; candidates:' not in str(exc.value)


def test_missing_cycle_keeps_scanning_parameters_after_its_back_edge() -> None:
    with pytest.raises(MissingProviderError) as exc:
        _ = Container().bind(_MissingCycleA).bind(_MissingCycleB).freeze()
    message = str(exc.value)
    assert '_MissingCycleDependency' in message
    assert '0 missing providers' not in message


def test_missing_provider_message_uses_the_key_at_both_ends_of_its_chain() -> None:
    class Missing: ...

    class Dependency:
        def __init__(self, missing: Missing) -> None: ...

    class Root:
        def __init__(self, dependency: Dependency) -> None: ...

    with pytest.raises(MissingProviderError) as exc:
        _ = Container().bind(Dependency).bind(Root).freeze()
    message = str(exc.value)
    assert 'no provider for ' in message
    path = message.split('resolution chain: ', 1)[1].removesuffix(')')
    assert [step.rsplit('.', 1)[-1] for step in path.split(' -> ')] == ['Root', 'Dependency', 'Missing']


def test_captive_message_names_both_remediation_targets() -> None:
    class Session: ...

    class Service:
        def __init__(self, session: Session) -> None: ...

    with pytest.raises(CaptiveDependencyError) as exc:
        _ = Container().bind(Session, scope=Scope.SCOPED).bind(Service, scope=Scope.SINGLETON).freeze()
    message = str(exc.value)
    assert "scope's test_captive_message_names_both_remediation_targets.<locals>.Session and reuse" in message
    remediation = message.split('Make ', 1)[1]
    assert remediation.endswith(
        'Service scoped, or test_captive_message_names_both_remediation_targets.<locals>.Session a singleton.'
    )


def test_captive_check_keeps_scanning_after_a_repeated_transient_dependency() -> None:
    class Transient: ...

    class Session: ...

    class Service:
        def __init__(self, first: Transient, second: Transient, session: Session) -> None: ...

    registry = (
        Registry()
        .bind(Transient, scope=Scope.TRANSIENT)
        .bind(Session, scope=Scope.SCOPED)
        .bind(Service, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError, match='Session'):
        _ = build_plan(registry.records())
