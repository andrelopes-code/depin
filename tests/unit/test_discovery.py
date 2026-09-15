"""Declarative provider values, ownership, and immutable composition."""

import inspect
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError
from typing import Protocol, assert_type, runtime_checkable

import pytest

from depin._core import discovery as discovery_module
from depin._core.discovery import Catalog, Manifest, Provider, provider
from depin._core.markers import provides
from depin._core.scope import Scope
from depin._core.spec import BindRecord
from depin.errors import InvalidProviderError

_DATA_ATTRIBUTE = '_data'
_MANIFEST_MODULE_ATTRIBUTE = '_manifest_module'
_MODULE_ATTRIBUTE = '_module'
_PROVIDERS_ATTRIBUTE = '_providers'
_SOURCES_ATTRIBUTE = '_sources'
_TOKEN_ATTRIBUTE = '_ProviderToken'
_DELETE_ATTRIBUTE = object()


class Service: ...


class _LocationView(Protocol):
    module: str
    filename: str
    line: int


@runtime_checkable
class _ProviderDataView(Protocol):
    target: object
    scope: Scope
    provides: object | None
    tag: str | None
    condition: object | None
    check: object | None
    owner: str
    location: _LocationView


def make_service(name: str) -> Service:
    del name
    return Service()


async def make_service_async(name: str) -> Service:
    del name
    return Service()


def generate_service(name: str) -> Generator[Service, None, None]:
    del name
    yield Service()


async def generate_service_async(name: str) -> AsyncGenerator[Service, None]:
    del name
    yield Service()


@contextmanager
def manage_service(name: str) -> Generator[Service, None, None]:
    del name
    yield Service()


@asynccontextmanager
async def manage_service_async(name: str) -> AsyncGenerator[Service, None]:
    del name
    yield Service()


def declared_provider_types() -> None:
    assert_type(provider(Service), Provider[Service])
    assert_type(provider(make_service), Provider[Service])
    assert_type(provider(make_service_async), Provider[Service])
    assert_type(provider(generate_service), Provider[Service])
    assert_type(provider(generate_service_async), Provider[Service])
    assert_type(provider(manage_service), Provider[Service])
    assert_type(provider(manage_service_async), Provider[Service])

    sync_manager: Callable[[str], AbstractContextManager[Service]] = manage_service
    async_manager: Callable[[str], AbstractAsyncContextManager[Service]] = manage_service_async
    assert_type(provider(sync_manager), Provider[Service])
    assert_type(provider(async_manager), Provider[Service])


def _call(callable_: Callable[..., object], arguments: tuple[object, ...]) -> object:
    # codeql[py/call/wrong-arguments] -- negative tests require invalid calls.
    return callable_(*arguments)


def _call_with_keywords(callable_: Callable[..., object], keywords: dict[str, object]) -> object:
    return callable_(**keywords)


def _provider_data(declaration: object) -> _ProviderDataView:
    snapshot: object = getattr(declaration, _DATA_ATTRIBUTE)
    if not isinstance(snapshot, _ProviderDataView):
        pytest.fail('Provider does not expose its private immutable snapshot')
    return snapshot


def _corrupt_attribute(target: object, attribute: str, replacement: object) -> None:
    if replacement is _DELETE_ATTRIBUTE:
        object.__delattr__(target, attribute)
    else:
        object.__setattr__(target, attribute, replacement)


def _private_provider_token() -> object:
    token_type: object = getattr(discovery_module, _TOKEN_ATTRIBUTE)
    if not callable(token_type):
        pytest.fail('_ProviderToken is not callable')
    return token_type()


def _foreign_discovery_values() -> tuple[Provider[object], Catalog, Manifest]:
    namespace: dict[str, object] = {
        '__name__': 'foreign_discovery_module',
        'Catalog': Catalog,
        'Manifest': Manifest,
        'Service': Service,
        'provider': provider,
    }
    exec(
        'declaration = provider(Service)\n'
        'catalog = Catalog(__name__, declaration)\n'
        'manifest = Manifest(__name__, catalog)',
        namespace,
    )
    catalog = namespace['catalog']
    manifest = namespace['manifest']
    if not isinstance(catalog, Catalog):
        pytest.fail('foreign catalogue is not a Catalog')
    if not isinstance(manifest, Manifest):
        pytest.fail('foreign manifest is not a Manifest')
    return catalog.providers[0], catalog, manifest


def test_provider_stores_the_exact_target_and_location() -> None:
    frame = inspect.currentframe()
    if frame is None:
        pytest.fail('inspect.currentframe() did not expose the test frame')
    declaration_line = frame.f_lineno + 1
    declaration = provider(Service)
    data = _provider_data(declaration)

    assert data.target is Service
    assert data.owner == __name__
    assert data.location.module == __name__
    assert data.location.filename == __file__
    assert data.location.line == declaration_line


def test_provider_rejects_a_missing_caller_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_frame() -> None:
        return None

    monkeypatch.setattr(inspect, 'currentframe', no_frame)

    with pytest.raises(InvalidProviderError, match='cannot determine the declaration or composition module'):
        provider(Service)


def test_provider_rejects_a_caller_without_a_module_name() -> None:
    namespace: dict[str, object] = {'Service': Service, 'provider': provider}

    with pytest.raises(InvalidProviderError, match='caller has no non-empty __name__'):
        exec('provider(Service)', namespace)


def test_provider_is_frozen_and_slotted() -> None:
    declaration = provider(Service)

    with pytest.raises(FrozenInstanceError):
        setattr(declaration, _DATA_ATTRIBUTE, _provider_data(declaration))
    assert not hasattr(declaration, '__dict__')


@pytest.mark.parametrize('target', [None, 42, object()], ids=['none', 'integer', 'instance'])
def test_provider_rejects_unsupported_targets(target: object) -> None:
    with pytest.raises(InvalidProviderError, match='pass a class or callable'):
        _call(provider, (target,))


@pytest.mark.parametrize(
    'arguments',
    [(), (object(),), (_private_provider_token(),)],
    ids=['no-arguments', 'foreign-token', 'private-token'],
)
def test_provider_rejects_direct_construction(arguments: tuple[object, ...]) -> None:
    with pytest.raises(InvalidProviderError, match=r'use provider\(target\)'):
        _call(Provider, arguments)


def configured_provider_types() -> None:
    declaration = provider(Service)

    def check_service(service: Service) -> bool:
        del service
        return True

    assert_type(declaration.configure(check=check_service), Provider[Service])


def test_provider_configure_replaces_all_metadata_without_mutating_the_original() -> None:
    class Contract: ...

    condition_calls = 0
    check_calls = 0

    def condition() -> bool:
        nonlocal condition_calls
        condition_calls += 1
        return True

    def check(service: Service) -> bool:
        nonlocal check_calls
        check_calls += 1
        del service
        return True

    declaration = provider(Service)
    original = _provider_data(declaration)

    configured = declaration.configure(
        scope=Scope.SCOPED,
        provides=Contract,
        tag='primary',
        when=condition,
        check=check,
    )
    configured_data = _provider_data(configured)

    assert configured is not declaration
    assert configured_data.target is Service
    assert configured_data.scope is Scope.SCOPED
    assert configured_data.provides is Contract
    assert configured_data.tag == 'primary'
    assert configured_data.condition is condition
    assert configured_data.check is check
    assert configured_data.owner == original.owner
    assert configured_data.location is original.location
    assert original.scope is Scope.SINGLETON
    assert original.provides is None
    assert original.tag is None
    assert original.condition is None
    assert original.check is None
    assert condition_calls == 0
    assert check_calls == 0


def test_provider_configure_resets_omitted_metadata_on_a_later_call() -> None:
    class Contract: ...

    def condition() -> bool:
        return True

    def check(service: Service) -> bool:
        del service
        return True

    first = provider(Service).configure(
        scope=Scope.TRANSIENT,
        provides=Contract,
        tag='temporary',
        when=condition,
        check=check,
    )

    second = first.configure()
    data = _provider_data(second)

    assert data.scope is Scope.SINGLETON
    assert data.provides is None
    assert data.tag is None
    assert data.condition is None
    assert data.check is None


def test_provider_configure_from_another_module_retains_declaration_ownership() -> None:
    declaration = provider(Service)
    original = _provider_data(declaration)
    namespace: dict[str, object] = {'__name__': 'foreign_configuration', 'declaration': declaration}

    exec("configured = declaration.configure(tag='foreign')", namespace)
    configured = namespace['configured']
    data = _provider_data(configured)

    assert data.owner == __name__
    assert data.location is original.location


def test_provider_configure_preserves_provides_marker_applied_before_declaration() -> None:
    class Contract: ...

    @provides(Contract)
    class Implementation: ...

    declaration = provider(Implementation).configure(tag='before')

    assert _provider_data(declaration).target is Implementation


def test_provider_configure_preserves_provides_marker_applied_after_declaration() -> None:
    class Contract: ...

    class Implementation: ...

    declaration = provider(Implementation).configure(tag='after')
    marked = provides(Contract)(Implementation)

    assert marked is Implementation
    assert _provider_data(declaration).target is Implementation


@pytest.mark.parametrize(
    ('keyword', 'value'),
    [
        ('scope', 'singleton'),
        ('provides', object()),
        ('tag', 1),
        ('when', object()),
        ('check', object()),
    ],
)
def test_provider_configure_rejects_invalid_runtime_metadata(keyword: str, value: object) -> None:
    declaration = provider(Service)

    with pytest.raises(InvalidProviderError, match=keyword):
        _call_with_keywords(declaration.configure, {keyword: value})


def catalog_and_manifest_types() -> None:
    declaration = provider(Service)
    catalog = Catalog(__name__, declaration)
    manifest = Manifest(__name__, catalog)

    assert_type(catalog.module, str)
    assert_type(catalog.providers, tuple[Provider[object], ...])
    assert_type(manifest.module, str)
    assert_type(manifest.sources, tuple[Catalog | Manifest, ...])
    assert_type(manifest.records(), Iterable[BindRecord])


def test_catalog_is_an_immutable_ordered_provider_snapshot() -> None:
    first = provider(Service)
    second = provider(ValueError)

    catalog = Catalog(__name__, first, second, first)

    assert catalog.module == __name__
    assert catalog.providers == (first, second, first)
    assert catalog.providers[0] is catalog.providers[2]
    assert catalog.providers is catalog.providers
    with pytest.raises(FrozenInstanceError):
        setattr(catalog, _MODULE_ATTRIBUTE, 'changed')
    assert not hasattr(catalog, '__dict__')


def test_catalog_accepts_imported_targets_declared_locally() -> None:
    declaration = provider(ValueError)

    catalog = Catalog(__name__, declaration)

    assert catalog.providers == (declaration,)
    assert _provider_data(declaration).owner == __name__


def test_catalog_allows_multiple_local_snapshots() -> None:
    first = provider(Service)
    second = provider(ValueError)

    services = Catalog(__name__, first)
    complete = Catalog(__name__, second, first)

    assert services.providers == (first,)
    assert complete.providers == (second, first)


def test_manifest_is_an_immutable_ordered_cross_module_snapshot() -> None:
    _, foreign_catalog, foreign_manifest = _foreign_discovery_values()
    local_catalog = Catalog(__name__, provider(Service))

    manifest = Manifest(__name__, foreign_catalog, foreign_manifest, local_catalog, foreign_catalog)

    assert manifest.module == __name__
    assert manifest.sources == (foreign_catalog, foreign_manifest, local_catalog, foreign_catalog)
    assert manifest.sources[0] is manifest.sources[3]
    assert manifest.sources is manifest.sources
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, _MODULE_ATTRIBUTE, 'changed')
    assert not hasattr(manifest, '__dict__')


@pytest.mark.parametrize('value', ['', 'forged.module'])
@pytest.mark.parametrize('constructor', [Catalog, Manifest], ids=['catalog', 'manifest'])
def test_catalog_and_manifest_reject_invalid_constructor_owner(constructor: Callable[..., object], value: str) -> None:
    with pytest.raises(InvalidProviderError) as exc:
        _call(constructor, (value,))

    message = str(exc.value)
    assert repr(value) in message
    assert repr(__name__) in message
    assert '__name__' in message


@pytest.mark.parametrize('constructor', [Catalog, Manifest], ids=['catalog', 'manifest'])
def test_catalog_and_manifest_reject_non_string_owner(constructor: Callable[..., object]) -> None:
    with pytest.raises(InvalidProviderError, match='non-empty __name__'):
        _call(constructor, (None,))


def test_catalog_rejects_a_foreign_provider_even_after_local_configuration() -> None:
    foreign, _, _ = _foreign_discovery_values()
    configured = foreign.configure(tag='configured-locally')

    with pytest.raises(InvalidProviderError) as exc:
        Catalog(__name__, configured)

    message = str(exc.value)
    assert repr(__name__) in message
    assert repr('foreign_discovery_module') in message
    assert 'index 0' in message
    assert _provider_data(configured).location.filename in message
    assert 'completed Catalog' in message


def test_catalog_rejects_a_non_provider_member_with_actionable_context() -> None:
    member = object()

    with pytest.raises(InvalidProviderError) as exc:
        _call(Catalog, (__name__, member))

    message = str(exc.value)
    assert repr(__name__) in message
    assert 'index 0' in message
    assert repr(member) in message
    assert 'provider(target)' in message


def test_manifest_rejects_a_non_composition_member_with_actionable_context() -> None:
    member = object()

    with pytest.raises(InvalidProviderError) as exc:
        _call(Manifest, (__name__, member))

    message = str(exc.value)
    assert repr(__name__) in message
    assert 'index 0' in message
    assert repr(member) in message
    assert 'Catalog or Manifest' in message


def test_manifest_records_stage_flat_catalogues_field_for_field() -> None:
    class Contract: ...

    def enabled() -> bool:
        return True

    def healthy(service: Service) -> bool:
        del service
        return True

    service = provider(Service).configure(
        scope=Scope.SCOPED,
        provides=Contract,
        tag='primary',
        when=enabled,
        check=healthy,
    )
    error = provider(ValueError).configure(scope=Scope.TRANSIENT)
    manifest = Manifest(__name__, Catalog(__name__, service), Catalog(__name__, error))

    records = manifest.records()

    assert records == (
        BindRecord(
            source=Service,
            scope=Scope.SCOPED,
            provides=Contract,
            tag='primary',
            condition=enabled,
            check=healthy,
        ),
        BindRecord(
            source=ValueError,
            scope=Scope.TRANSIENT,
            provides=None,
            tag=None,
            condition=None,
            check=None,
        ),
    )


def test_manifest_records_flatten_nested_manifests_left_to_right() -> None:
    service = Catalog(__name__, provider(Service))
    runtime_error = Catalog(__name__, provider(RuntimeError))
    value_error = Catalog(__name__, provider(ValueError))
    nested = Manifest(__name__, runtime_error, Manifest(__name__, value_error))
    manifest = Manifest(__name__, service, nested, Catalog(__name__, provider(KeyError)))

    records = manifest.records()

    assert records == (
        BindRecord(Service, Scope.SINGLETON, None, None),
        BindRecord(RuntimeError, Scope.SINGLETON, None, None),
        BindRecord(ValueError, Scope.SINGLETON, None, None),
        BindRecord(KeyError, Scope.SINGLETON, None, None),
    )


def test_manifest_records_preserve_every_repeated_occurrence() -> None:
    service = Catalog(__name__, provider(Service))
    error = Catalog(__name__, provider(ValueError))
    nested = Manifest(__name__, error, service)
    manifest = Manifest(__name__, service, nested, service, nested)

    records = manifest.records()

    assert records == (
        BindRecord(Service, Scope.SINGLETON, None, None),
        BindRecord(ValueError, Scope.SINGLETON, None, None),
        BindRecord(Service, Scope.SINGLETON, None, None),
        BindRecord(Service, Scope.SINGLETON, None, None),
        BindRecord(ValueError, Scope.SINGLETON, None, None),
        BindRecord(Service, Scope.SINGLETON, None, None),
    )


def test_manifest_staging_rejects_a_forged_provider_snapshot_with_full_provenance() -> None:
    declaration = provider(Service)
    data = _provider_data(declaration)
    location = data.location
    catalog = Catalog(__name__, declaration)
    nested = Manifest(__name__, catalog)
    manifest = Manifest(__name__, nested)
    offending = object()
    object.__setattr__(data, 'target', offending)

    with pytest.raises(InvalidProviderError) as exc:
        manifest.records()

    message = str(exc.value)
    assert repr(manifest.module) in message
    assert 'source index 0' in message
    assert repr(catalog.module) in message
    assert 'provider index 0' in message
    assert f'{location.filename}:{location.line}' in message
    assert repr(offending) in message
    assert 'provider(target)' in message


@pytest.mark.parametrize(
    ('replacement', 'expected_context'),
    [
        pytest.param(_DELETE_ATTRIBUTE, 'no valid declaration snapshot', id='missing-data'),
        pytest.param(object(), 'invalid declaration data', id='invalid-data'),
    ],
)
def test_catalog_rejects_a_malformed_private_provider_snapshot(
    replacement: object,
    expected_context: str,
) -> None:
    declaration = provider(Service)
    _corrupt_attribute(declaration, _DATA_ATTRIBUTE, replacement)

    with pytest.raises(InvalidProviderError) as exc:
        Catalog(__name__, declaration)

    message = str(exc.value)
    assert expected_context in message
    assert 'provider(target)' in message


@pytest.mark.parametrize(
    ('target_name', 'attribute', 'replacement', 'expected_context'),
    [
        pytest.param(
            'manifest', _MODULE_ATTRIBUTE, _DELETE_ATTRIBUTE, 'no valid module snapshot', id='manifest-module-missing'
        ),
        pytest.param('manifest', _MODULE_ATTRIBUTE, None, 'invalid module', id='manifest-module-invalid'),
        pytest.param(
            'manifest', _SOURCES_ATTRIBUTE, _DELETE_ATTRIBUTE, 'no valid source snapshot', id='manifest-sources-missing'
        ),
        pytest.param('manifest', _SOURCES_ATTRIBUTE, [], 'invalid source snapshot', id='manifest-sources-invalid'),
        pytest.param('manifest', _SOURCES_ATTRIBUTE, (object(),), 'source index 0', id='manifest-member-invalid'),
        pytest.param(
            'catalog', _MODULE_ATTRIBUTE, _DELETE_ATTRIBUTE, 'no valid catalogue snapshot', id='catalog-module-missing'
        ),
        pytest.param('catalog', _MODULE_ATTRIBUTE, None, 'invalid catalogue owner', id='catalog-module-invalid'),
        pytest.param(
            'catalog',
            _PROVIDERS_ATTRIBUTE,
            _DELETE_ATTRIBUTE,
            'no valid catalogue snapshot',
            id='catalog-providers-missing',
        ),
        pytest.param('catalog', _PROVIDERS_ATTRIBUTE, [], 'invalid provider snapshot', id='catalog-providers-invalid'),
        pytest.param('catalog', _PROVIDERS_ATTRIBUTE, (object(),), 'provider index 0', id='catalog-member-invalid'),
    ],
)
def test_manifest_staging_rejects_malformed_private_composition_snapshots(
    target_name: str,
    attribute: str,
    replacement: object,
    expected_context: str,
) -> None:
    catalog = Catalog(__name__, provider(Service))
    manifest = Manifest(__name__, catalog)
    target = manifest if target_name == 'manifest' else catalog
    _corrupt_attribute(target, attribute, replacement)

    with pytest.raises(InvalidProviderError) as exc:
        manifest.records()

    message = str(exc.value)
    assert expected_context in message
    assert 'recreate' in message


@pytest.mark.parametrize(
    ('corruption', 'expected_context'),
    [
        ('missing-data', 'no valid declaration snapshot'),
        ('invalid-data', 'invalid declaration snapshot'),
        ('invalid-location', 'invalid declaration location'),
        ('empty-location-module', 'invalid declaration location'),
        ('empty-location-filename', 'invalid declaration location'),
        ('zero-location-line', 'invalid declaration location'),
        ('boolean-location-line', 'invalid declaration location'),
        ('owner-mismatch', 'not catalogue owner'),
        ('location-owner-mismatch', 'not declaration owner'),
        ('invalid-metadata', 'invalid metadata'),
    ],
)
def test_manifest_staging_rejects_malformed_private_provider_records(
    corruption: str,
    expected_context: str,
) -> None:
    declaration = provider(Service)
    data = _provider_data(declaration)
    location = data.location
    catalog = Catalog(__name__, declaration)
    manifest = Manifest(__name__, catalog)

    if corruption == 'missing-data':
        object.__delattr__(declaration, _DATA_ATTRIBUTE)
    elif corruption == 'invalid-data':
        object.__setattr__(declaration, _DATA_ATTRIBUTE, object())
    elif corruption == 'invalid-location':
        object.__setattr__(data, 'location', object())
    elif corruption == 'empty-location-module':
        object.__setattr__(location, 'module', '')
    elif corruption == 'empty-location-filename':
        object.__setattr__(location, 'filename', '')
    elif corruption == 'zero-location-line':
        object.__setattr__(location, 'line', 0)
    elif corruption == 'boolean-location-line':
        object.__setattr__(location, 'line', True)
    elif corruption == 'owner-mismatch':
        object.__setattr__(data, 'owner', 'foreign.module')
    elif corruption == 'location-owner-mismatch':
        object.__setattr__(location, 'module', 'foreign.module')
    else:
        object.__setattr__(data, 'scope', object())

    with pytest.raises(InvalidProviderError) as exc:
        manifest.records()

    message = str(exc.value)
    assert repr(manifest.module) in message
    assert 'source index 0' in message
    assert 'provider index 0' in message
    assert expected_context in message
    assert 'recreate' in message.lower()


def test_manifest_staging_rejects_a_recursive_private_snapshot() -> None:
    manifest = Manifest(__name__)
    object.__setattr__(manifest, _SOURCES_ATTRIBUTE, (manifest,))

    with pytest.raises(InvalidProviderError) as exc:
        manifest.records()

    message = str(exc.value)
    assert 'recursive manifest composition' in message
    assert 'source index 0' in message


def test_manifest_staging_rejects_an_owner_that_changes_during_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = Manifest(__name__)
    original_manifest_module: object = getattr(discovery_module, _MANIFEST_MODULE_ATTRIBUTE)
    if callable(original_manifest_module):
        call_manifest_module = original_manifest_module
    else:
        pytest.fail('_manifest_module is not callable')
    calls = 0

    def changing_manifest_module(value: Manifest, context: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            return 'changed.module'
        module: object = call_manifest_module(value, context)
        if not isinstance(module, str):
            pytest.fail('_manifest_module did not return a module name')
        return module

    monkeypatch.setattr(discovery_module, _MANIFEST_MODULE_ATTRIBUTE, changing_manifest_module)

    with pytest.raises(InvalidProviderError) as exc:
        manifest.records()

    message = str(exc.value)
    assert 'has changed owner to' in message
    assert repr(__name__) in message
    assert repr('changed.module') in message
