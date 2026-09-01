"""`conformance/coverage.toml` carries a type-test decision for every public symbol.

The map is what stops a new public symbol landing with no consumer-typing
decision behind it: this module enumerates the public surface and fails when a
name has no entry, and fails the other way when an entry names a symbol that is
no longer public.

Three sources, not one. `depin.__all__` and `depin.errors` are imported —
`depin.errors` needs no framework, and its eleven exceptions are in no
``__all__`` while four of them inherit a builtin as well, which decides what a
consumer's existing ``except TypeError`` now catches. `depin/ext/` is **parsed
with `ast` and never imported**, because this module runs on the free-threaded
and pre-release jobs where no framework is installed;
`tests/unit/test_integration_contract.py` uses the same technique.

Class-member inventory is out of scope, and `conformance/README.md` records that
as a decision. Adding ``Container.foo()`` passes this gate; the corpus is what
guards members, by exercising them.
"""

import ast
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeGuard

import pytest

import depin
import depin.errors
import depin.ext

ROOT: Final = Path(__file__).resolve().parents[2]
COVERAGE: Final = ROOT / 'conformance' / 'coverage.toml'
CONFORMANCE: Final = ROOT / 'conformance'


def declared_all(body: list[ast.stmt]) -> tuple[str, ...] | None:
    """The strings in a module-level ``__all__``, or `None` when it declares none.

    Only `depin/ext/fastapi.py` declares one, and honouring it is what makes
    `Inject` findable: the module has no top-level `Inject` at all.
    """
    for node in body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.List | ast.Tuple):
            return tuple(
                item.value for item in value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
    return None


def assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def collect(body: list[ast.stmt], found: list[str]) -> None:
    """Every name a module body binds at the top level, `If` branches included.

    Descending into `If` bodies **and their `else` branches** is what finds a
    symbol declared under `TYPE_CHECKING`. A module-level ``import X as Y`` is a
    binding rather than an import here, because that is how three framework
    modules publish their base class.
    """
    for node in body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            found.append(node.name)
        elif isinstance(node, ast.TypeAlias):
            found.append(node.name.id)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            found.extend(assigned_names(node))
        elif isinstance(node, ast.Import | ast.ImportFrom):
            found.extend(alias.asname for alias in node.names if alias.asname is not None)
        elif isinstance(node, ast.If):
            collect(node.body, found)
            collect(node.orelse, found)


def module_symbols(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    exported = declared_all(tree.body)
    if exported is not None:
        return exported
    found: list[str] = []
    collect(tree.body, found)
    return tuple(sorted({name for name in found if not name.startswith('_')}))


def integration_modules() -> list[Path]:
    return sorted(Path(depin.ext.__file__).parent.glob('*.py'))


def error_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, value in vars(depin.errors).items()
            if not name.startswith('_') and isinstance(value, type) and issubclass(value, BaseException)
        )
    )


def public_surface() -> tuple[str, ...]:
    names = [*depin.__all__]
    names.extend(f'depin.errors.{name}' for name in error_names())
    for path in integration_modules():
        names.extend(f'depin.ext.{path.stem}.{name}' for name in module_symbols(path.read_text(encoding='utf-8')))
    return tuple(names)


def is_table(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def is_array(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def entries() -> Mapping[str, Mapping[str, object]]:
    with COVERAGE.open('rb') as handle:
        document: object = tomllib.load(handle)
    if not is_table(document):
        raise TypeError(f'{COVERAGE} is not a table')
    return {name: value for name, value in document.items() if is_table(value)}


def named_fixtures(record: Mapping[str, object]) -> list[str]:
    listed = record.get('fixtures', [])
    if not is_array(listed):
        raise TypeError('a coverage entry\'s "fixtures" must be an array of strings')
    paths: list[str] = []
    for item in listed:
        if not isinstance(item, str):
            raise TypeError('a coverage entry\'s "fixtures" must be an array of strings')
        paths.append(item)
    return paths


@pytest.mark.parametrize('name', public_surface())
def test_every_public_symbol_has_a_coverage_entry(name: str) -> None:
    assert name in entries(), (
        f'{name} is public but conformance/coverage.toml carries no entry for it; '
        'add the fixtures that exercise it, or a decision and a reason'
    )


def test_no_coverage_entry_names_a_symbol_that_is_not_public() -> None:
    assert sorted(set(entries()) - set(public_surface())) == []


@pytest.mark.parametrize('name', sorted(entries()))
def test_every_entry_names_fixtures_or_records_a_decision(name: str) -> None:
    record = entries()[name]

    assert 'fixtures' in record or 'decision' in record, f'{name} carries neither fixtures nor a decision'
    if 'decision' in record:
        assert record.get('reason'), f'{name} records a decision with no reason'


@pytest.mark.parametrize('name', sorted(entries()))
def test_every_fixture_a_coverage_entry_names_exists(name: str) -> None:
    missing = [fixture for fixture in named_fixtures(entries()[name]) if not (CONFORMANCE / fixture).is_file()]

    assert missing == [], f'{name} names fixtures that do not exist: {missing}'


def test_the_scan_covers_the_fastapi_integration() -> None:
    """Guards the scan itself: an empty or mis-rooted glob must fail loudly, not skip."""
    assert 'fastapi.py' in {path.name for path in integration_modules()}


def test_the_scanner_finds_a_symbol_declared_only_under_type_checking() -> None:
    """`ext/fastapi.py` has no top-level `Inject`: its body is `__all__` plus one `If`."""
    source = (Path(depin.ext.__file__).parent / 'fastapi.py').read_text(encoding='utf-8')
    top_level = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef | ast.TypeAlias)]

    assert top_level == []
    assert 'Inject' in module_symbols(source)


def test_the_scanner_finds_both_branches_of_a_type_checking_split() -> None:
    source = (
        'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    type Inject[T] = T\nelse:\n    class Inject: ...\n'
    )

    assert module_symbols(source) == ('Inject',)


def test_the_scanner_finds_a_module_level_type_alias() -> None:
    """`ext/asgi.py` declares two PEP 695 aliases at module level and `ext/wsgi.py` one."""
    asgi = module_symbols((Path(depin.ext.__file__).parent / 'asgi.py').read_text(encoding='utf-8'))
    wsgi = module_symbols((Path(depin.ext.__file__).parent / 'wsgi.py').read_text(encoding='utf-8'))

    assert {'Message', 'ASGIScope'} <= set(asgi)
    assert 'Environ' in wsgi


def test_the_scanner_treats_an_aliased_import_as_a_symbol() -> None:
    """Three framework modules publish their base as `RequestScope as ASGIRequestScope`."""
    source = 'from depin.ext.asgi import RequestScope as ASGIRequestScope\n'

    assert module_symbols(source) == ('ASGIRequestScope',)


def test_the_scanner_does_not_treat_a_plain_import_as_a_symbol() -> None:
    source = 'import contextlib\nfrom depin import Host\n'

    assert module_symbols(source) == ()


def test_the_scanner_honours_a_declared_all_over_the_module_body() -> None:
    source = "__all__ = ['Kept']\nclass Kept: ...\nclass Dropped: ...\n"

    assert module_symbols(source) == ('Kept',)


def test_the_scanner_skips_underscore_prefixed_names() -> None:
    source = 'class _Private: ...\ndef _helper() -> None: ...\nclass Public: ...\n'

    assert module_symbols(source) == ('Public',)


def test_the_error_scan_finds_every_exception_in_the_module() -> None:
    names = error_names()

    assert 'DepinError' in names
    assert len(names) == len([name for name in dir(depin.errors) if not name.startswith('_')])
