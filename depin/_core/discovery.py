"""Typed immutable declarations for explicit provider discovery."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Iterable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from types import FrameType
from typing import Never, Self, TypeGuard, overload, override

from depin._core.scope import Scope
from depin._core.spec import BindRecord, Condition, ProviderKey
from depin._core.typeguards import is_provider_key
from depin.errors import InvalidProviderError


class _ProviderToken:
    __slots__ = ()


class _ProviderMeta(type):
    @override
    def __call__(cls, *args: object, **kwargs: object) -> Never:
        del cls, args, kwargs
        raise InvalidProviderError('Provider cannot be constructed directly; use provider(target) instead.')


@dataclass(frozen=True, slots=True)
class _SourceLocation:
    module: str
    filename: str
    line: int


@dataclass(frozen=True, slots=True)
class _ProviderData:
    target: object
    scope: Scope
    provides: ProviderKey | None
    tag: str | None
    condition: Condition | None
    check: object | None
    owner: str
    location: _SourceLocation


def _caller_location() -> _SourceLocation:
    frame = inspect.currentframe()
    public_frame: FrameType | None = None
    caller: FrameType | None = None
    try:
        if frame is not None:
            public_frame = frame.f_back
        if public_frame is not None:
            caller = public_frame.f_back
        if caller is None:
            raise InvalidProviderError(
                'cannot determine the declaration or composition module; create discovery values from a Python module.'
            )
        module = caller.f_globals.get('__name__')
        if not isinstance(module, str) or not module:
            raise InvalidProviderError(
                'cannot determine the declaration or composition module because the caller has no non-empty __name__; '
                'create discovery values from a Python module.'
            )
        return _SourceLocation(module=module, filename=caller.f_code.co_filename, line=caller.f_lineno)
    finally:
        del caller, public_frame, frame


@dataclass(frozen=True, slots=True, init=False)
class Provider[T](metaclass=_ProviderMeta):
    """An immutable declaration created only by `provider()`.

    The declaration retains the exact target identity and its declaration-site
    ownership. Calling ``Provider(...)`` directly is invalid; use
    ``provider(target)`` so depin can capture that provenance.

    Raises:
        InvalidProviderError: The class is constructed directly instead of
            through `provider()`.

    Example:
        ```pycon
        >>> from depin import Provider, provider
        >>> class Service: ...
        >>> declaration = provider(Service)
        >>> isinstance(declaration, Provider)
        True

        ```
    """

    _data: _ProviderData = field(repr=False)

    def __new__(cls, _token: _ProviderToken, /) -> Self:
        del _token
        return object.__new__(cls)

    def configure[U](
        self: Provider[U],
        *,
        scope: Scope = Scope.SINGLETON,
        provides: ProviderKey | None = None,
        tag: str | None = None,
        when: Condition | None = None,
        check: Callable[[U], object] | None = None,
    ) -> Provider[U]:
        """Return a new declaration whose metadata replaces the current metadata.

        Omitted arguments reset to their defaults. Conditions and health checks
        are stored without being evaluated; `Container.freeze()` evaluates the
        condition, and the frozen container runs the check.

        Args:
            scope: Lifetime to apply to the produced value.
            provides: Explicit key, replacing inference from the target.
            tag: Disambiguator for other providers under the same key.
            when: Condition deciding whether the binding enters the plan.
            check: Health check associated with the produced value.

        Returns:
            A new immutable declaration retaining the original target and
            declaration location.

        Raises:
            InvalidProviderError: Any metadata value violates its contract.

        Example:
            ```pycon
            >>> from depin import Scope, provider
            >>> class Service: ...
            >>> base = provider(Service)
            >>> configured = base.configure(scope=Scope.TRANSIENT, tag='worker')
            >>> configured is base
            False

            ```
        """
        _validate_metadata(scope, provides, tag, when, check)
        data = _ProviderData(
            target=self._data.target,
            scope=scope,
            provides=provides,
            tag=tag,
            condition=when,
            check=check,
            owner=self._data.owner,
            location=self._data.location,
        )
        return _allocate_provider(type(self), data)


def _allocate_provider[T](provider_type: type[Provider[T]], data: _ProviderData) -> Provider[T]:
    declaration = object.__new__(provider_type)
    object.__setattr__(declaration, '_data', data)
    return declaration


def _validate_metadata(
    scope: object,
    provides: object,
    tag: object,
    when: object,
    check: object,
) -> None:
    if not isinstance(scope, Scope):
        raise InvalidProviderError(f'cannot use {scope!r} as provider scope; pass a Scope value.')
    if provides is not None and not is_provider_key(provides):
        raise InvalidProviderError(
            f'cannot use {provides!r} as provider provides metadata; pass a valid ProviderKey or None.'
        )
    if tag is not None and not isinstance(tag, str):
        raise InvalidProviderError(f'cannot use {tag!r} as provider tag; pass a string or None.')
    if when is not None and not isinstance(when, bool) and not callable(when):
        raise InvalidProviderError(
            f'cannot use {when!r} as provider when metadata; pass a bool, a zero-argument callable, or None.'
        )
    if check is not None and not callable(check):
        raise InvalidProviderError(f'cannot use {check!r} as provider check; pass a callable or None.')


@overload
def provider[T](target: type[T], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, Generator[T, None, None]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AsyncGenerator[T, None]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AbstractContextManager[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AbstractAsyncContextManager[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, Awaitable[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, T], /) -> Provider[T]: ...


def provider(target: type[object] | Callable[..., object], /) -> Provider[object]:
    """Capture one provider target without wrapping or replacing its identity.

    Declaration records only the explicit target and its source location. It
    performs no scanning, condition evaluation, provider analysis, or import.

    Args:
        target: Class or factory to declare.

    Returns:
        An immutable declaration ready for optional `Provider.configure()` and
        inclusion in its owning module's `Catalog`.

    Raises:
        InvalidProviderError: The target is neither a class nor callable, or the
            declaration module cannot be determined.

    Example:
        ```pycon
        >>> from depin import Provider, provider
        >>> class Service: ...
        >>> declaration = provider(Service)
        >>> isinstance(declaration, Provider)
        True

        ```
    """
    if not isinstance(target, type) and not callable(target):
        raise InvalidProviderError(f'cannot declare {target!r} as a provider; pass a class or callable instead.')
    location = _caller_location()
    data = _ProviderData(
        target=target,
        scope=Scope.SINGLETON,
        provides=None,
        tag=None,
        condition=None,
        check=None,
        owner=location.module,
        location=location,
    )
    return _allocate_provider(Provider, data)


def _validated_owner(kind: str, supplied: object, caller: str) -> str:
    if not isinstance(supplied, str) or not supplied or supplied != caller:
        raise InvalidProviderError(
            f'cannot create {kind} for module {supplied!r} from caller {caller!r}; '
            "pass the caller module's non-empty __name__ as the first argument."
        )
    return supplied


def _is_provider(value: object) -> TypeGuard[Provider[object]]:
    return isinstance(value, Provider)


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _catalog_member(owner: str, index: int, declaration: object) -> None:
    if not _is_provider(declaration):
        raise InvalidProviderError(
            f'Catalog {owner!r} provider at index {index} is {declaration!r}; '
            'pass a Provider created with provider(target).'
        )
    try:
        snapshot: object = object.__getattribute__(declaration, '_data')
    except AttributeError as exc:
        raise InvalidProviderError(
            f'Catalog {owner!r} provider at index {index} has no valid declaration snapshot; '
            'pass a Provider created with provider(target).'
        ) from exc
    if not isinstance(snapshot, _ProviderData):
        raise InvalidProviderError(
            f'Catalog {owner!r} provider at index {index} has invalid declaration data {snapshot!r}; '
            'pass a Provider created with provider(target).'
        )
    if snapshot.owner != owner:
        raise InvalidProviderError(
            f'Catalog {owner!r} provider at index {index} was declared by {snapshot.owner!r} at '
            f'{snapshot.location.filename}:{snapshot.location.line}; keep the declaration in its owning module, '
            'construct a completed Catalog there, and import that completed Catalog.'
        )


def _manifest_member(owner: str, index: int, source: object) -> None:
    if not isinstance(source, Catalog | Manifest):
        raise InvalidProviderError(
            f'Manifest {owner!r} source at index {index} is {source!r}; pass a Catalog or Manifest.'
        )


@dataclass(frozen=True, slots=True)
class _StagingPath:
    manifests: tuple[str, ...]
    source_indexes: tuple[int, ...]

    @classmethod
    def root(cls, module: str) -> Self:
        return cls((module,), ())

    def nested(self, source_index: int, module: str) -> Self:
        return type(self)((*self.manifests, module), (*self.source_indexes, source_index))

    def describe(self) -> str:
        parts = [f'Manifest {self.manifests[0]!r}']
        for source_index, module in zip(self.source_indexes, self.manifests[1:], strict=True):
            parts.append(f'source index {source_index} -> Manifest {module!r}')
        return ' -> '.join(parts)

    def source(self, source_index: int) -> str:
        return f'{self.describe()} -> source index {source_index}'


@dataclass(frozen=True, slots=True, init=False)
class Catalog:
    """An immutable ordered declaration snapshot kept by its owning module.

    A catalogue records only local `Provider` declarations. It is not a
    `Bindings` source: composition roots explicitly place completed catalogues
    inside a `Manifest` before ingestion.
    """

    _module: str
    _providers: tuple[Provider[object], ...]

    def __init__(self, module: str, /, *providers: Provider[object]) -> None:
        """Create the completed snapshot for its owning module.

        Args:
            module: The caller's module name, conventionally ``__name__``.
            *providers: Local declarations in their desired lexical order.

        Raises:
            InvalidProviderError: The owner is not the caller, a member is not a
                declaration, or a declaration belongs to another module.

        Example:
            ```pycon
            >>> from depin import Catalog, provider
            >>> class Service: ...
            >>> declaration = provider(Service)
            >>> providers = Catalog(__name__, declaration)
            >>> providers.providers == (declaration,)
            True

            ```
        """
        caller = _caller_location()
        owner = _validated_owner('Catalog', module, caller.module)
        for index, declaration in enumerate(providers):
            _catalog_member(owner, index, declaration)
        object.__setattr__(self, '_module', owner)
        object.__setattr__(self, '_providers', providers)

    @property
    def module(self) -> str:
        return self._module

    @property
    def providers(self) -> tuple[Provider[object], ...]:
        return self._providers


@dataclass(frozen=True, slots=True, init=False)
class Manifest:
    """An immutable ordered composition of catalogues and nested manifests.

    A manifest is the explicit discovery boundary and satisfies `Bindings`.
    Sources flatten left-to-right; repeated occurrences remain repeated. No
    package scan, name search, or de-duplication occurs.
    """

    _module: str
    _sources: tuple[Catalog | Manifest, ...]

    def __init__(self, module: str, /, *sources: Catalog | Manifest) -> None:
        """Create an explicit composition snapshot.

        Args:
            module: The caller's module name, conventionally ``__name__``.
            *sources: Completed catalogues or manifests in ingestion order.

        Raises:
            InvalidProviderError: The owner is not the caller or a source is not
                a completed `Catalog` or `Manifest`.

        Example:
            ```pycon
            >>> from depin import Catalog, Manifest, provider
            >>> class Service: ...
            >>> providers = Catalog(__name__, provider(Service))
            >>> manifest = Manifest(__name__, providers)
            >>> manifest.sources == (providers,)
            True

            ```
        """
        caller = _caller_location()
        owner = _validated_owner('Manifest', module, caller.module)
        for index, source in enumerate(sources):
            _manifest_member(owner, index, source)
        object.__setattr__(self, '_module', owner)
        object.__setattr__(self, '_sources', sources)

    @property
    def module(self) -> str:
        return self._module

    @property
    def sources(self) -> tuple[Catalog | Manifest, ...]:
        return self._sources

    def records(self) -> Iterable[BindRecord]:
        """Flatten every occurrence into one complete record tuple.

        Staging preserves lexical order and every repetition, then discards
        discovery provenance. Conditions and checks are copied but not run.

        Returns:
            Ordinary records ready for one atomic collector append.

        Raises:
            InvalidProviderError: A forged or otherwise malformed snapshot is
                detected before any tuple is returned.

        Example:
            ```pycon
            >>> from depin import Catalog, Manifest, provider
            >>> class Service: ...
            >>> providers = Catalog(__name__, provider(Service))
            >>> leaf = Manifest(__name__, providers)
            >>> records = Manifest(__name__, leaf, leaf).records()
            >>> [record.source for record in records] == [Service, Service]
            True

            ```
        """
        return _stage_manifest(self)


def _manifest_module(manifest: Manifest, context: str) -> str:
    try:
        module: object = object.__getattribute__(manifest, '_module')
    except AttributeError as exc:
        raise InvalidProviderError(
            f'{context} has no valid module snapshot; recreate the Manifest from completed Catalog or Manifest values.'
        ) from exc
    if not isinstance(module, str) or not module:
        raise InvalidProviderError(
            f'{context} has invalid module {module!r}; recreate the Manifest with its owning module __name__.'
        )
    return module


def _manifest_sources(manifest: Manifest, path: _StagingPath) -> tuple[Catalog | Manifest, ...]:
    try:
        snapshot: object = object.__getattribute__(manifest, '_sources')
    except AttributeError as exc:
        raise InvalidProviderError(
            f'{path.describe()} has no valid source snapshot; '
            'recreate the Manifest from completed Catalog or Manifest values.'
        ) from exc
    if not _is_object_tuple(snapshot):
        raise InvalidProviderError(
            f'{path.describe()} has invalid source snapshot {snapshot!r}; '
            'recreate the Manifest from completed Catalog or Manifest values.'
        )
    sources: list[Catalog | Manifest] = []
    for index in range(len(snapshot)):
        source: object = snapshot[index]
        if not isinstance(source, Catalog | Manifest):
            raise InvalidProviderError(
                f'{path.source(index)} is {source!r}; recreate the Manifest with a completed Catalog or Manifest.'
            )
        sources.append(source)
    return tuple(sources)


def _catalog_providers(catalog: Catalog, context: str) -> tuple[str, tuple[Provider[object], ...]]:
    try:
        owner: object = object.__getattribute__(catalog, '_module')
        snapshot: object = object.__getattribute__(catalog, '_providers')
    except AttributeError as exc:
        raise InvalidProviderError(
            f'{context} has no valid catalogue snapshot; recreate the Catalog in its owning module.'
        ) from exc
    if not isinstance(owner, str) or not owner:
        raise InvalidProviderError(
            f'{context} has invalid catalogue owner {owner!r}; recreate the Catalog with its owning module __name__.'
        )
    catalog_context = f'{context} -> Catalog {owner!r}'
    if not _is_object_tuple(snapshot):
        raise InvalidProviderError(
            f'{catalog_context} has invalid provider snapshot {snapshot!r}; '
            'recreate the Catalog from Provider values created with provider(target).'
        )
    declarations: list[Provider[object]] = []
    for index in range(len(snapshot)):
        declaration: object = snapshot[index]
        if not _is_provider(declaration):
            raise InvalidProviderError(
                f'{catalog_context} provider index {index} is {declaration!r}; '
                'recreate the Catalog from Provider values created with provider(target).'
            )
        declarations.append(declaration)
    return owner, tuple(declarations)


def _provider_record(declaration: Provider[object], owner: str, context: str, index: int) -> BindRecord:
    provider_context = f'{context} provider index {index}'
    try:
        snapshot: object = object.__getattribute__(declaration, '_data')
    except AttributeError as exc:
        raise InvalidProviderError(
            f'{provider_context} has no valid declaration snapshot; recreate it with provider(target).'
        ) from exc
    if not isinstance(snapshot, _ProviderData):
        raise InvalidProviderError(
            f'{provider_context} has invalid declaration snapshot {snapshot!r}; recreate it with provider(target).'
        )
    location: object = object.__getattribute__(snapshot, 'location')
    if not isinstance(location, _SourceLocation):
        raise InvalidProviderError(
            f'{provider_context} has invalid declaration location {location!r}; recreate it with provider(target).'
        )
    location_module: object = object.__getattribute__(location, 'module')
    filename: object = object.__getattribute__(location, 'filename')
    line: object = object.__getattribute__(location, 'line')
    if (
        not isinstance(location_module, str)
        or not location_module
        or not isinstance(filename, str)
        or not filename
        or not isinstance(line, int)
        or isinstance(line, bool)
        or line < 1
    ):
        raise InvalidProviderError(
            f'{provider_context} has invalid declaration location {location!r}; recreate it with provider(target).'
        )
    declared_at = f'{filename}:{line}'
    declaration_owner: object = object.__getattribute__(snapshot, 'owner')
    if not isinstance(declaration_owner, str) or not declaration_owner or declaration_owner != owner:
        raise InvalidProviderError(
            f'{provider_context} declared at {declared_at} has owner {declaration_owner!r}, '
            f'not catalogue owner {owner!r}; '
            'recreate the declaration and completed Catalog in the same owning module.'
        )
    if location_module != declaration_owner:
        raise InvalidProviderError(
            f'{provider_context} declared at {declared_at} has location module {location_module!r}, '
            f'not declaration owner {declaration_owner!r}; recreate it with provider(target).'
        )
    if not isinstance(snapshot.target, type) and not callable(snapshot.target):
        raise InvalidProviderError(
            f'{provider_context} declared at {declared_at} has invalid target {snapshot.target!r}; '
            'recreate it with provider(target).'
        )
    try:
        _validate_metadata(snapshot.scope, snapshot.provides, snapshot.tag, snapshot.condition, snapshot.check)
    except InvalidProviderError as exc:
        raise InvalidProviderError(
            f'{provider_context} declared at {declared_at} has invalid metadata: {exc} '
            'Recreate it with provider(target).configure(...).'
        ) from exc
    return _bind_record(snapshot)


def _bind_record(snapshot: _ProviderData) -> BindRecord:
    """Create a record across the runtime representation boundary for generic keys."""
    record = BindRecord(
        source=snapshot.target,
        scope=snapshot.scope,
        provides=None,
        tag=snapshot.tag,
        condition=snapshot.condition,
        check=snapshot.check,
    )
    object.__setattr__(record, 'provides', snapshot.provides)
    return record


def _stage_catalog(catalog: Catalog, path: _StagingPath, source_index: int, staged: list[BindRecord]) -> None:
    context = path.source(source_index)
    owner, declarations = _catalog_providers(catalog, context)
    catalog_context = f'{context} -> Catalog {owner!r}'
    for index, declaration in enumerate(declarations):
        staged.append(_provider_record(declaration, owner, catalog_context, index))


def _stage_manifest_into(
    manifest: Manifest,
    path: _StagingPath,
    staged: list[BindRecord],
    active: set[int],
) -> None:
    identity = id(manifest)
    if identity in active:
        raise InvalidProviderError(
            f'{path.describe()} creates a recursive manifest composition; rebuild it from completed acyclic snapshots.'
        )
    active.add(identity)
    try:
        module = _manifest_module(manifest, path.describe())
        if module != path.manifests[-1]:
            raise InvalidProviderError(
                f'{path.describe()} has changed owner to {module!r}; recreate the Manifest in its owning module.'
            )
        for source_index, source in enumerate(_manifest_sources(manifest, path)):
            if isinstance(source, Catalog):
                _stage_catalog(source, path, source_index, staged)
                continue
            nested_module = _manifest_module(source, path.source(source_index))
            _stage_manifest_into(source, path.nested(source_index, nested_module), staged, active)
    finally:
        active.remove(identity)


def _stage_manifest(manifest: Manifest) -> tuple[BindRecord, ...]:
    module = _manifest_module(manifest, 'Manifest staging root')
    path = _StagingPath.root(module)
    staged: list[BindRecord] = []
    _stage_manifest_into(manifest, path, staged, set())
    return tuple(staged)
