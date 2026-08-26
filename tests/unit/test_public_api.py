"""The public surface: what `depin` exports, and what it reports as its version."""

import importlib
import importlib.metadata

import pytest

import depin

EXPECTED_EXPORTS = (
    'Bindings',
    'Container',
    'FrozenContainer',
    'Named',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'Tag',
    'Token',
    'injected',
    'provides',
)


def test_all_is_sorted_and_complete() -> None:
    assert depin.__all__ == EXPECTED_EXPORTS
    assert list(depin.__all__) == sorted(depin.__all__)


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
