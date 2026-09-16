"""The public surface: what `depin` exports, and what it reports as its version."""

import importlib
import importlib.metadata
import inspect

import pytest

import depin
from depin.errors import InvalidProviderError

EXPECTED_EXPORTS = (
    'CONTRACT_VERSION',
    'AsyncInSyncContextError',
    'Bindings',
    'Catalog',
    'Condition',
    'Container',
    'ContainerClosedError',
    'ContainerLifecycleError',
    'ContractVersion',
    'DependencyGraph',
    'FastAPIIntegrationError',
    'FrozenContainer',
    'GraphEdge',
    'GraphNode',
    'HealthCheck',
    'HealthReport',
    'HealthResult',
    'Host',
    'Manifest',
    'Named',
    'Provider',
    'ProviderKey',
    'ProviderOverride',
    'ProviderShape',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'ScopeSeed',
    'ScopeSeeder',
    'Tag',
    'Token',
    'Underlying',
    'WarmupReport',
    'hosted_container',
    'injected',
    'optional_hosted_container',
    'provider',
    'provides',
    'render_key',
)


def test_all_is_complete() -> None:
    assert depin.__all__ == EXPECTED_EXPORTS


@pytest.mark.parametrize('name', EXPECTED_EXPORTS)
def test_every_exported_name_is_importable(name: str) -> None:
    assert hasattr(depin, name)


def test_the_core_imports_no_third_party_package() -> None:
    """`depin` must stay dependency-free; only `depin.ext` may import a framework."""
    import sys

    before = set(sys.modules)
    _ = importlib.reload(depin)
    imported = set(sys.modules) - before
    assert not {name for name in imported if name.split('.')[0] in {'fastapi', 'starlette', 'pydantic'}}


def test_version_is_a_nonempty_string() -> None:
    assert isinstance(depin.__version__, str)
    assert depin.__version__


def test_version_falls_back_when_the_distribution_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_installed(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, 'version', not_installed)
    try:
        reloaded = importlib.reload(depin)
        assert reloaded.__version__ == '0.0.0+unknown'
    finally:
        monkeypatch.undo()
        _ = importlib.reload(depin)

    assert depin.__version__ != '0.0.0+unknown'


def test_provider_shape_is_exported_with_the_alias_member() -> None:
    assert depin.ProviderShape.ALIAS.value == 'alias'


def test_provider_shape_is_exported_with_the_collection_member() -> None:
    assert depin.ProviderShape.COLLECTION.value == 'collection'


def _public_value(path: str) -> object:
    value: object = depin
    for part in path.split('.'):
        value = getattr(value, part)
    return value


@pytest.mark.parametrize(
    ('path', 'required'),
    [
        ('Provider', ('immutable', 'exact target identity', 'ownership', 'Raises:', 'Example:')),
        ('Provider.configure', ('replaces', 'immutable', 'freeze()', 'Args:', 'Returns:', 'Raises:', 'Example:')),
        ('provider', ('identity', 'no scanning', 'owning module', 'Args:', 'Returns:', 'Raises:', 'Example:')),
        ('Catalog', ('immutable', 'owning module', 'ordered', 'Bindings', 'Raises:', 'Example:')),
        ('Catalog.__init__', ('owner', 'lexical order', 'Args:', 'Raises:', 'Example:')),
        (
            'Manifest',
            ('immutable', 'Bindings', 'nested', 'left-to-right', 'repeated', 'package scan', 'Raises:', 'Example:'),
        ),
        ('Manifest.__init__', ('owner', 'ingestion order', 'Args:', 'Raises:', 'Example:')),
        ('Manifest.records', ('flatten', 'lexical order', 'repetition', 'not run', 'Returns:', 'Raises:', 'Example:')),
    ],
)
def test_declarative_discovery_public_docstrings_define_their_contract(
    path: str,
    required: tuple[str, ...],
) -> None:
    doc = inspect.getdoc(_public_value(path))

    assert doc is not None
    for fragment in required:
        assert fragment.casefold() in doc.casefold()


def test_existing_public_docs_integrate_manifest_ingestion_and_discovery_failures() -> None:
    contracts = (
        (inspect.getdoc(depin), ('provider', 'Catalog', 'Manifest', 'freeze')),
        (inspect.getdoc(depin.Container), ('Manifest', 'Bindings')),
        (inspect.getdoc(depin.Registry), ('Catalog', 'Manifest')),
        (inspect.getdoc(depin.Bindings), ('Manifest',)),
        (inspect.getdoc(depin.Container.include), ('Manifest', 'atomic', 'InvalidProviderError')),
        (inspect.getdoc(InvalidProviderError), ('provider', 'Catalog', 'Manifest', 'records', 'Example:')),
    )

    for doc, fragments in contracts:
        assert doc is not None
        for fragment in fragments:
            assert fragment.casefold() in doc.casefold()
