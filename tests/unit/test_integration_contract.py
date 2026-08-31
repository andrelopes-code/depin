"""No integration under `depin/ext/` may reach into `depin._core`."""

import ast
from pathlib import Path

import pytest

import depin
import depin.ext

_EXT_PACKAGE = 'depin.ext'


def _absolute(module: str | None, level: int, package: str) -> str:
    if level == 0:
        return module or ''
    parts = package.split('.')
    base = '.'.join(parts[: len(parts) - level + 1])
    return f'{base}.{module}' if module else base


def imported_modules(source: str, package: str) -> tuple[str, ...]:
    """Every module name a source file imports, with relative imports made absolute."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(_absolute(node.module, node.level, package))
    return tuple(names)


def public_names_imported_from_depin(source: str, package: str) -> tuple[str, ...]:
    """Every name imported directly out of the `depin` package."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and _absolute(node.module, node.level, package) == 'depin':
            names.extend(alias.name for alias in node.names)
    return tuple(names)


def reaches_into_core(source: str, package: str) -> tuple[str, ...]:
    return tuple(
        name for name in imported_modules(source, package) if name == 'depin._core' or name.startswith('depin._core.')
    )


def _integration_modules() -> list[Path]:
    return sorted(path for path in Path(depin.ext.__file__).parent.rglob('*.py'))


def test_the_scan_covers_the_fastapi_integration() -> None:
    """Guards the scan itself: an empty or mis-rooted glob must fail loudly, not skip."""
    assert 'fastapi.py' in {path.name for path in _integration_modules()}


def test_the_scanner_reports_a_module_that_imports_depin_core() -> None:
    source = 'from depin._core.frozen import FrozenContainer\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.frozen',)


def test_the_scanner_reports_a_relative_reach_into_depin_core() -> None:
    source = 'from .._core.scope import ScopeFrame\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.scope',)


def test_the_scanner_reports_a_plain_import_of_depin_core() -> None:
    source = 'import depin._core.frozen\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.frozen',)


def test_the_scanner_accepts_the_public_package() -> None:
    source = 'from depin import Host, hosted_container\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ()


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_no_integration_reaches_into_depin_core(path: Path) -> None:
    assert reaches_into_core(path.read_text(), _EXT_PACKAGE) == ()


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_no_integration_names_depin_core_at_all(path: Path) -> None:
    """Catches an attribute walk (`depin._core.frozen`) that the import scan cannot see.

    Deliberately a literal-substring check: an integration's own prose (a
    docstring or comment) must not name the private package either, not just
    its import statements.
    """
    assert '_core' not in path.read_text(), f'{path} names depin._core'


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_every_name_an_integration_imports_from_depin_is_public(path: Path) -> None:
    imported = public_names_imported_from_depin(path.read_text(), _EXT_PACKAGE)

    assert [name for name in imported if name not in depin.__all__] == []
