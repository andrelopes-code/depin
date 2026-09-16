"""Collector and runtime boundaries for declarative manifests."""

from collections.abc import Callable

import pytest

from depin._core import discovery as discovery_module
from depin._core.container import Container
from depin._core.discovery import Catalog, Manifest, provider
from depin._core.markers import injected, provides
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord, Bindings
from depin.errors import DuplicateProviderError, MissingProviderError

type _DuplicateComposition = Callable[[type[object]], Container]


def _same_catalog_twice(service: type[object]) -> Container:
    catalog = Catalog(__name__, provider(service))
    return Container(Manifest(__name__, catalog, catalog))


def _same_manifest_twice(service: type[object]) -> Container:
    leaf = Manifest(__name__, Catalog(__name__, provider(service)))
    return Container(Manifest(__name__, leaf, leaf))


def _overlapping_manifests(service: type[object]) -> Container:
    first = Manifest(__name__, Catalog(__name__, provider(service)))
    second = Manifest(__name__, Catalog(__name__, provider(service)))
    return Container(Manifest(__name__, first, second))


def _manifest_and_manual_binding(service: type[object]) -> Container:
    manifest = Manifest(__name__, Catalog(__name__, provider(service)))
    return Container().include(manifest).bind(service)


def test_only_a_manifest_satisfies_the_bindings_runtime_boundary() -> None:
    catalog = Catalog(__name__, provider(ValueError))
    manifest = Manifest(__name__, catalog)

    assert not isinstance(catalog, Bindings)
    assert isinstance(manifest, Bindings)


@pytest.mark.asyncio
async def test_committed_manifest_records_leave_every_runtime_path_independent_of_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Singleton: ...

    class Scoped: ...

    catalog = Catalog(
        __name__,
        provider(Singleton),
        provider(Scoped).configure(scope=Scope.SCOPED),
    )
    container = Container(Manifest(__name__, catalog))

    def fail_staging(_manifest: Manifest) -> tuple[BindRecord, ...]:
        raise AssertionError('runtime returned to declarative staging')

    monkeypatch.setattr(discovery_module, '_stage_manifest', fail_staging)
    frozen = container.freeze()

    assert isinstance(frozen.resolve(Singleton), Singleton)
    assert isinstance(await frozen.aresolve(Singleton), Singleton)
    with frozen.scope():
        assert isinstance(frozen.resolve(Scoped), Scoped)
    async with frozen.ascope():
        assert isinstance(await frozen.aresolve(Scoped), Scoped)

    replacement = Singleton()
    with frozen.override(Singleton).using(replacement):
        assert frozen.resolve(Singleton) is replacement

    @frozen.inject
    def injected_singleton(value: Singleton = injected) -> Singleton:
        return value

    assert isinstance(injected_singleton(), Singleton)


def test_registry_include_accepts_a_manifest_as_a_bindings_source() -> None:
    manifest = Manifest(__name__, Catalog(__name__, provider(ValueError)))

    registry = Registry().include(manifest)

    assert registry.records() == (BindRecord(ValueError, Scope.SINGLETON, None, None),)


def test_manifest_records_remain_contiguous_between_manual_bindings() -> None:
    class ManualBefore: ...

    class DeclarativeFirst: ...

    class DeclarativeSecond: ...

    class ManualAfter: ...

    manifest = Manifest(
        __name__,
        Catalog(__name__, provider(DeclarativeFirst), provider(DeclarativeSecond)),
    )
    registry = Registry().bind(ManualBefore).include(manifest).bind(ManualAfter)
    container = Container(registry)

    assert tuple(record.source for record in registry.records()) == (
        ManualBefore,
        DeclarativeFirst,
        DeclarativeSecond,
        ManualAfter,
    )
    assert tuple(record.source for record in container.records()) == (
        ManualBefore,
        DeclarativeFirst,
        DeclarativeSecond,
        ManualAfter,
    )

    frozen = container.freeze()

    assert isinstance(frozen.resolve(ManualBefore), ManualBefore)
    assert isinstance(frozen.resolve(DeclarativeFirst), DeclarativeFirst)
    assert isinstance(frozen.resolve(DeclarativeSecond), DeclarativeSecond)
    assert isinstance(frozen.resolve(ManualAfter), ManualAfter)


def test_nested_manifests_flatten_left_to_right() -> None:
    class First: ...

    class Second: ...

    class Third: ...

    class Fourth: ...

    left = Manifest(__name__, Catalog(__name__, provider(First), provider(Second)))
    middle = Catalog(__name__, provider(Third))
    right = Manifest(__name__, Catalog(__name__, provider(Fourth)))
    manifest = Manifest(__name__, left, middle, right)

    assert tuple(record.source for record in manifest.records()) == (First, Second, Third, Fourth)


@pytest.mark.parametrize(
    'composition',
    [_same_catalog_twice, _same_manifest_twice, _overlapping_manifests, _manifest_and_manual_binding],
    ids=['same-catalog', 'same-manifest', 'overlapping-manifests', 'manual-overlap'],
)
def test_repeated_active_occurrences_reach_the_existing_duplicate_error(
    composition: _DuplicateComposition,
) -> None:
    class Service: ...

    container = composition(Service)

    assert tuple(record.source for record in container.records()) == (Service, Service)
    with pytest.raises(DuplicateProviderError, match='Service'):
        _ = container.freeze()


def test_distinct_tags_for_the_same_key_coexist() -> None:
    class Service: ...

    class Primary(Service): ...

    class Secondary(Service): ...

    manifest = Manifest(
        __name__,
        Catalog(
            __name__,
            provider(Primary).configure(provides=Service, tag='primary'),
            provider(Secondary).configure(provides=Service, tag='secondary'),
        ),
    )

    frozen = Container(manifest).freeze()

    assert isinstance(frozen.resolve(Service, tag='primary'), Primary)
    assert isinstance(frozen.resolve(Service, tag='secondary'), Secondary)


def test_an_inactive_declarative_collision_is_evaluated_only_at_freeze() -> None:
    class Service: ...

    class Inactive(Service): ...

    class Active(Service): ...

    calls = 0

    def disabled() -> bool:
        nonlocal calls
        calls += 1
        return False

    manifest = Manifest(
        __name__,
        Catalog(
            __name__,
            provider(Inactive).configure(provides=Service, when=disabled),
            provider(Active).configure(provides=Service),
        ),
    )
    container = Container(manifest)

    assert calls == 0
    assert tuple(record.source for record in container.records()) == (Inactive, Active)
    assert calls == 0

    frozen = container.freeze()

    assert calls == 1
    assert isinstance(frozen.resolve(Service), Active)


def test_declarative_check_identity_and_health_match_manual_binding() -> None:
    class Service: ...

    checked: list[Service] = []

    def healthy(service: Service) -> bool:
        checked.append(service)
        return True

    manifest = Manifest(__name__, Catalog(__name__, provider(Service).configure(check=healthy)))
    declarative = Container(manifest)
    manual = Container().bind(Service, check=healthy)
    (declarative_record,) = tuple(declarative.records())
    (manual_record,) = tuple(manual.records())

    assert declarative_record.check is manual_record.check is healthy

    declarative_frozen = declarative.freeze()
    manual_frozen = manual.freeze()
    declarative_value = declarative_frozen.resolve(Service)
    manual_value = manual_frozen.resolve(Service)

    assert declarative_frozen.checks() == manual_frozen.checks()
    assert declarative_frozen.health().results == manual_frozen.health().results
    assert checked[0] is declarative_value
    assert checked[1] is manual_value


def test_provides_marker_is_honoured_before_and_after_provider_capture() -> None:
    class BeforeContract: ...

    @provides(BeforeContract)
    class BeforeImplementation: ...

    before = provider(BeforeImplementation)

    class AfterContract: ...

    class AfterImplementation: ...

    after = provider(AfterImplementation)
    provides(AfterContract)(AfterImplementation)
    manifest = Manifest(__name__, Catalog(__name__, before, after))

    frozen = Container(manifest).freeze()

    assert isinstance(frozen.resolve(BeforeContract), BeforeImplementation)
    assert isinstance(frozen.resolve(AfterContract), AfterImplementation)


def test_an_existing_plan_ignores_a_later_provides_marker_change() -> None:
    class InitialContract: ...

    class LaterContract: ...

    class Implementation: ...

    declaration = provider(Implementation)
    provides(InitialContract)(Implementation)
    container = Container(Manifest(__name__, Catalog(__name__, declaration)))
    frozen = container.freeze()

    provides(LaterContract)(Implementation)

    assert isinstance(frozen.resolve(InitialContract), Implementation)
    with pytest.raises(MissingProviderError):
        _ = frozen.resolve(LaterContract)
    assert isinstance(container.freeze().resolve(LaterContract), Implementation)


def test_manifest_and_existing_plan_ignore_later_module_symbol_rebinding() -> None:
    class Original: ...

    class Reloaded: ...

    module_symbols: dict[str, type[object]] = {'Service': Original}
    declaration = provider(module_symbols['Service'])
    manifest = Manifest(__name__, Catalog(__name__, declaration))
    frozen = Container(manifest).freeze()

    module_symbols['Service'] = Reloaded

    (record,) = tuple(manifest.records())
    assert record.source is Original
    assert isinstance(frozen.resolve(Original), Original)
