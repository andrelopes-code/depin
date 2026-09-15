"""Explicit declarative imports across Python loader and installation layouts."""

import importlib
import importlib.abc
import importlib.util
import sys
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Protocol, override, runtime_checkable
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from depin import Container, Manifest
from tests.fixtures.discovery_imports.namespace.portion_a.discovery_namespace import first as namespace_first_fixture
from tests.fixtures.discovery_imports.regular import discovery_layout as regular_layout

_LAYOUT_PACKAGE = 'discovery_layout'
_NAMESPACE_PACKAGE = 'discovery_namespace'
_EXPECTED_ORDER = ('First', 'Second', 'Trapped')
_REGULAR_FILES = (
    '__init__.py',
    'application.py',
    'first.py',
    'reexports.py',
    'second.py',
    'trap.py',
    'unlisted.py',
)


@runtime_checkable
class _LayoutView(Protocol):
    First: type[object]
    FirstAlias: type[object]
    ReexportedFirst: type[object]
    manifest: Manifest
    reexported_manifest: Manifest

    def getattr_calls(self) -> int: ...


@runtime_checkable
class _ManifestModuleView(Protocol):
    manifest: Manifest


@runtime_checkable
class _TrapModuleView(Protocol):
    def getattr_calls(self) -> int: ...


def _module_file(module: ModuleType) -> Path:
    filename = module.__file__
    if filename is None:
        pytest.fail(f'{module.__name__} has no source file')
    return Path(filename)


_REGULAR_ROOT = _module_file(regular_layout).parent.parent
_NAMESPACE_ROOT = _module_file(namespace_first_fixture).parents[2]


def _forget_package(package: str) -> None:
    prefix = f'{package}.'
    for module_name in tuple(sys.modules):
        if module_name == package or module_name.startswith(prefix):
            del sys.modules[module_name]
    importlib.invalidate_caches()


def _layout_view(module: ModuleType) -> _LayoutView:
    if not isinstance(module, _LayoutView):
        pytest.fail(f'{module.__name__} does not expose the layout fixture contract')
    return module


def _manifest_module_view(module: ModuleType) -> _ManifestModuleView:
    if not isinstance(module, _ManifestModuleView):
        pytest.fail(f'{module.__name__} does not expose a manifest')
    return module


def _trap_module_view(module: ModuleType) -> _TrapModuleView:
    if not isinstance(module, _TrapModuleView):
        pytest.fail(f'{module.__name__} does not expose the getattr trap counter')
    return module


def _manifest_sources(manifest: Manifest) -> tuple[type[object], ...]:
    sources: list[type[object]] = []
    for record in manifest.records():
        if not isinstance(record.source, type):
            pytest.fail(f'fixture record source is not a class: {record.source!r}')
        sources.append(record.source)
    return tuple(sources)


def _assert_explicit_order(manifest: Manifest) -> None:
    sources = _manifest_sources(manifest)
    assert tuple(source.__name__ for source in sources) == _EXPECTED_ORDER

    frozen = Container(manifest).freeze()
    for source in sources:
        assert isinstance(frozen.resolve(source), source)


def _assert_regular_layout(layout: _LayoutView) -> None:
    _assert_explicit_order(layout.manifest)
    assert layout.FirstAlias is layout.First
    assert layout.ReexportedFirst is layout.First
    assert layout.reexported_manifest is layout.manifest
    assert layout.getattr_calls() == 0

    package = layout.manifest.module.rsplit('.', 1)[0]
    assert f'{package}.unlisted' not in sys.modules


@contextmanager
def _temporary_sys_path(*paths: Path) -> Generator[None, None, None]:
    original = sys.path.copy()
    sys.path[:0] = [str(path) for path in paths]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path[:] = original
        importlib.invalidate_caches()


@contextmanager
def _layout_from_path(path: Path) -> Generator[_LayoutView, None, None]:
    _forget_package(_LAYOUT_PACKAGE)
    with _temporary_sys_path(path):
        try:
            yield _layout_view(importlib.import_module(_LAYOUT_PACKAGE))
        finally:
            _forget_package(_LAYOUT_PACKAGE)


def _write_archive(path: Path, *, wheel: bool) -> None:
    with ZipFile(path, 'w', compression=ZIP_DEFLATED) as archive:
        for filename in _REGULAR_FILES:
            archive.writestr(f'{_LAYOUT_PACKAGE}/{filename}', (_REGULAR_ROOT / _LAYOUT_PACKAGE / filename).read_bytes())
        if wheel:
            archive.writestr(
                'discovery_layout_fixture-0.0.dist-info/WHEEL',
                'Wheel-Version: 1.0\nGenerator: depin tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
            )
            archive.writestr(
                'discovery_layout_fixture-0.0.dist-info/METADATA',
                'Metadata-Version: 2.1\nName: discovery-layout-fixture\nVersion: 0.0\n',
            )
            archive.writestr('discovery_layout_fixture-0.0.dist-info/RECORD', '')


def _loader_sources() -> dict[str, bytes]:
    sources: dict[str, bytes] = {}
    for filename in _REGULAR_FILES:
        module_suffix = '' if filename == '__init__.py' else f'.{filename.removesuffix(".py")}'
        sources[f'{_LAYOUT_PACKAGE}{module_suffix}'] = (_REGULAR_ROOT / _LAYOUT_PACKAGE / filename).read_bytes()
    return sources


class _ExactNameLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, sources: Mapping[str, bytes]) -> None:
        self._sources = sources
        self.requested: list[str] = []

    @override
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        del path, target
        if fullname not in self._sources:
            return None
        self.requested.append(fullname)
        return importlib.util.spec_from_loader(fullname, self, is_package=fullname == _LAYOUT_PACKAGE)

    @override
    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        del spec
        return None

    @override
    def exec_module(self, module: ModuleType) -> None:
        source = self._sources[module.__name__]
        code = compile(source, f'<exact-loader:{module.__name__}>', 'exec')
        exec(code, module.__dict__)


@contextmanager
def _layout_from_loader(loader: _ExactNameLoader) -> Generator[_LayoutView, None, None]:
    _forget_package(_LAYOUT_PACKAGE)
    sys.meta_path.insert(0, loader)
    try:
        yield _layout_view(importlib.import_module(_LAYOUT_PACKAGE))
    finally:
        sys.meta_path.remove(loader)
        _forget_package(_LAYOUT_PACKAGE)


def test_regular_package_uses_only_explicit_manifest_imports() -> None:
    _assert_regular_layout(_layout_view(regular_layout))


def test_namespace_portions_use_only_explicit_manifest_imports() -> None:
    _forget_package(_NAMESPACE_PACKAGE)
    with _temporary_sys_path(
        _NAMESPACE_ROOT / 'portion_a',
        _NAMESPACE_ROOT / 'portion_b',
        _NAMESPACE_ROOT / 'portion_unused',
    ):
        try:
            application = _manifest_module_view(importlib.import_module(f'{_NAMESPACE_PACKAGE}.application'))
            trap = _trap_module_view(importlib.import_module(f'{_NAMESPACE_PACKAGE}.trap'))

            _assert_explicit_order(application.manifest)
            assert trap.getattr_calls() == 0
            assert f'{_NAMESPACE_PACKAGE}.unlisted' not in sys.modules
        finally:
            _forget_package(_NAMESPACE_PACKAGE)


def test_editable_tree_import_uses_the_fixture_bytes() -> None:
    with _layout_from_path(_REGULAR_ROOT) as layout:
        _assert_regular_layout(layout)


def test_wheel_shaped_zip_import_uses_the_fixture_bytes(tmp_path: Path) -> None:
    wheel = tmp_path / 'discovery_layout_fixture-0.0-py3-none-any.whl'
    _write_archive(wheel, wheel=True)

    with _layout_from_path(wheel) as layout:
        _assert_regular_layout(layout)


def test_plain_zip_import_uses_the_fixture_bytes(tmp_path: Path) -> None:
    archive = tmp_path / 'discovery-layout.zip'
    _write_archive(archive, wheel=False)

    with _layout_from_path(archive) as layout:
        _assert_regular_layout(layout)


def test_exact_name_loader_needs_no_enumeration_or_package_walk() -> None:
    loader = _ExactNameLoader(_loader_sources())

    with _layout_from_loader(loader) as layout:
        _assert_regular_layout(layout)

    assert set(loader.requested) == {
        'discovery_layout',
        'discovery_layout.application',
        'discovery_layout.first',
        'discovery_layout.reexports',
        'discovery_layout.second',
        'discovery_layout.trap',
    }
    assert len(loader.requested) == len(set(loader.requested))


def test_alias_and_reexport_preserve_target_and_manifest_identity() -> None:
    assert regular_layout.FirstAlias is regular_layout.First
    assert regular_layout.ReexportedFirst is regular_layout.First
    assert regular_layout.reexported_manifest is regular_layout.manifest


def test_module_getattr_is_not_probed() -> None:
    assert regular_layout.getattr_calls() == 0
