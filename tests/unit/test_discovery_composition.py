"""Collector and runtime boundaries for declarative manifests."""

import pytest

from depin._core import discovery as discovery_module
from depin._core.container import Container
from depin._core.discovery import Catalog, Manifest, provider
from depin._core.markers import injected
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord, Bindings


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
