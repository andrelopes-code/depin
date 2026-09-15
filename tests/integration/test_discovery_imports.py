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
from typing import Protocol, TypeGuard, override, runtime_checkable
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from depin import Catalog, Container, Manifest
from depin.errors import MissingProviderError
from tests.fixtures.discovery_imports.cycles.early import state as early_cycle_state_fixture
from tests.fixtures.discovery_imports.cycles.partial import state as partial_cycle_state_fixture
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
_SUPPORTED_FIRST = 'tests.fixtures.discovery_imports.cycles.supported.first'
_SUPPORTED_SECOND = 'tests.fixtures.discovery_imports.cycles.supported.second'
_EARLY_FIRST = 'tests.fixtures.discovery_imports.cycles.early.first'
_EARLY_SECOND = 'tests.fixtures.discovery_imports.cycles.early.second'
_PARTIAL_APPLICATION = 'tests.fixtures.discovery_imports.cycles.partial.application'
_PARTIAL_DECLARATIONS = 'tests.fixtures.discovery_imports.cycles.partial.declarations'
_PARTIAL_FAILURE = 'tests.fixtures.discovery_imports.cycles.partial.failure'
_MISSING_MODULE_ATTRIBUTE = object()


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


@runtime_checkable
class _SupportedFirstView(Protocol):
    First: type[object]
    first_catalog: Catalog
    manifest: Manifest


@runtime_checkable
class _SupportedSecondView(Protocol):
    Second: type[object]
    second_catalog: Catalog

    def observed_first(self) -> type[object]: ...

    def observed_declaration(self) -> object: ...


def _is_layout_view(value: object) -> TypeGuard[_LayoutView]:
    return isinstance(value, _LayoutView)


def _is_manifest_module_view(value: object) -> TypeGuard[_ManifestModuleView]:
    return isinstance(value, _ManifestModuleView)


def _is_trap_module_view(value: object) -> TypeGuard[_TrapModuleView]:
    return isinstance(value, _TrapModuleView)


def _is_supported_first_view(value: object) -> TypeGuard[_SupportedFirstView]:
    return isinstance(value, _SupportedFirstView)


def _is_supported_second_view(value: object) -> TypeGuard[_SupportedSecondView]:
    return isinstance(value, _SupportedSecondView)


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
    if not _is_layout_view(module):
        pytest.fail(f'{module.__name__} does not expose the layout fixture contract')
    return module


def _manifest_module_view(module: ModuleType) -> _ManifestModuleView:
    if not _is_manifest_module_view(module):
        pytest.fail(f'{module.__name__} does not expose a manifest')
    return module


def _trap_module_view(module: ModuleType) -> _TrapModuleView:
    if not _is_trap_module_view(module):
        pytest.fail(f'{module.__name__} does not expose the getattr trap counter')
    return module


def _supported_first_view(module: ModuleType) -> _SupportedFirstView:
    if not _is_supported_first_view(module):
        pytest.fail(f'{module.__name__} does not expose the supported-cycle first-module contract')
    return module


def _supported_second_view(module: ModuleType) -> _SupportedSecondView:
    if not _is_supported_second_view(module):
        pytest.fail(f'{module.__name__} does not expose the supported-cycle second-module contract')
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
def _isolated_modules(*module_names: str) -> Generator[None, None, None]:
    saved_modules = {name: sys.modules[name] for name in module_names if name in sys.modules}
    saved_attributes: list[tuple[ModuleType, str, object]] = []
    for name in module_names:
        parent_name, _, attribute = name.rpartition('.')
        parent = sys.modules.get(parent_name)
        if parent is not None:
            saved_attributes.append((parent, attribute, getattr(parent, attribute, _MISSING_MODULE_ATTRIBUTE)))
            if hasattr(parent, attribute):
                delattr(parent, attribute)
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        for parent, attribute, value in saved_attributes:
            if value is _MISSING_MODULE_ATTRIBUTE:
                if hasattr(parent, attribute):
                    delattr(parent, attribute)
            else:
                setattr(parent, attribute, value)
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


@pytest.mark.parametrize('entry_module', [_SUPPORTED_FIRST, _SUPPORTED_SECOND], ids=['first', 'second'])
def test_supported_import_cycle_uses_names_bound_before_the_cycle(entry_module: str) -> None:
    with _isolated_modules(_SUPPORTED_FIRST, _SUPPORTED_SECOND):
        importlib.import_module(entry_module)
        first = _supported_first_view(sys.modules[_SUPPORTED_FIRST])
        second = _supported_second_view(sys.modules[_SUPPORTED_SECOND])

        assert second.observed_first() is first.First
        assert second.observed_declaration() is first.first_catalog.providers[0]
        assert first.manifest.sources == (first.first_catalog, second.second_catalog)
        assert _manifest_sources(first.manifest) == (first.First, second.Second)

        frozen = Container(first.manifest).freeze()
        assert isinstance(frozen.resolve(first.First), first.First)
        assert isinstance(frozen.resolve(second.Second), second.Second)


def test_early_import_cycle_preserves_the_original_exception_and_cause() -> None:
    early_cycle_state_fixture.active = True
    try:
        with _isolated_modules(_EARLY_FIRST, _EARLY_SECOND):
            with pytest.raises(early_cycle_state_fixture.EarlyCycleError, match=r'before first\.ready existed') as exc:
                importlib.import_module(_EARLY_FIRST)

            assert exc.value.__cause__ is early_cycle_state_fixture.cause
            assert _EARLY_FIRST not in sys.modules
            assert _EARLY_SECOND not in sys.modules
    finally:
        early_cycle_state_fixture.active = False


def test_partial_import_failure_publishes_nothing_and_leaves_receiver_unchanged() -> None:
    receiver = partial_cycle_state_fixture.receiver
    before = receiver.records()

    partial_cycle_state_fixture.active = True
    try:
        with _isolated_modules(_PARTIAL_APPLICATION, _PARTIAL_DECLARATIONS, _PARTIAL_FAILURE):
            with pytest.raises(partial_cycle_state_fixture.PartialImportError, match='fixture import stopped') as exc:
                importlib.import_module(_PARTIAL_APPLICATION)

            assert exc.value.__cause__ is partial_cycle_state_fixture.cause
            assert partial_cycle_state_fixture.published_manifest is None
            assert receiver.records() == before
            assert _PARTIAL_APPLICATION not in sys.modules
            assert _PARTIAL_FAILURE not in sys.modules
    finally:
        partial_cycle_state_fixture.active = False


def test_reload_creates_new_snapshots_without_changing_existing_consumers() -> None:
    with _isolated_modules(_SUPPORTED_FIRST, _SUPPORTED_SECOND):
        first_module = importlib.import_module(_SUPPORTED_FIRST)
        second_module = importlib.import_module(_SUPPORTED_SECOND)
        first = _supported_first_view(first_module)
        second = _supported_second_view(second_module)

        old_manifest = first.manifest
        old_catalogues = old_manifest.sources
        old_declarations = (first.first_catalog.providers[0], second.second_catalog.providers[0])
        old_targets = _manifest_sources(old_manifest)
        builder = Container(old_manifest)
        builder_records = builder.records()
        frozen = builder.freeze()
        old_plan: object = object.__getattribute__(frozen, '_plan')

        reloaded_second = _supported_second_view(importlib.reload(second_module))
        reloaded_first = _supported_first_view(importlib.reload(first_module))
        new_manifest = reloaded_first.manifest
        new_catalogues = new_manifest.sources
        new_declarations = (
            reloaded_first.first_catalog.providers[0],
            reloaded_second.second_catalog.providers[0],
        )
        new_targets = _manifest_sources(new_manifest)

        assert new_manifest is not old_manifest
        assert all(new is not old for new, old in zip(new_catalogues, old_catalogues, strict=True))
        assert all(new is not old for new, old in zip(new_declarations, old_declarations, strict=True))
        assert all(new is not old for new, old in zip(new_targets, old_targets, strict=True))

        assert old_manifest.sources == old_catalogues
        assert _manifest_sources(old_manifest) == old_targets
        assert all(current is old for current, old in zip(builder.records(), builder_records, strict=True))
        assert tuple(record.source for record in builder.records()) == old_targets
        assert object.__getattribute__(frozen, '_plan') is old_plan
        for target in old_targets:
            assert isinstance(frozen.resolve(target), target)
        for target in new_targets:
            with pytest.raises(MissingProviderError):
                frozen.resolve(target)

        new_builder = Container(new_manifest)
        new_frozen = new_builder.freeze()
        assert tuple(record.source for record in new_builder.records()) == new_targets
        assert object.__getattribute__(new_frozen, '_plan') is not old_plan
        for target in new_targets:
            assert isinstance(new_frozen.resolve(target), target)
