from typing import TypeGuard, overload

from depin._core.introspect import is_object_token
from depin._core.markers import Token
from depin._core.scope import Scope, ScopeFrame
from depin._core.spec import ProviderKey, ProviderShape, ProviderSpec, ResolutionPlan
from depin.errors import AsyncInSyncContextError, MissingProviderError


class FrozenContainer:
    """Immutable view of a resolved dependency graph.

    The internal resolver carries provider results as `object` because the
    graph spec is type-erased; the public API (`__getitem__`, `resolve`,
    `aresolve`) re-states the static result type. The narrowing is a single
    documented boundary: providers must produce values matching the static
    type of their declared key.
    """

    __slots__ = ('_plan', '_root')

    def __init__(self, plan: ResolutionPlan) -> None:
        self._plan = plan
        self._root = ScopeFrame()

    @overload
    def __getitem__[T](self, key: type[T]) -> T: ...
    @overload
    def __getitem__[T](self, key: Token[T]) -> T: ...
    def __getitem__[T](self, key: type[T] | Token[T]) -> T:
        return self.resolve(key)

    def resolve[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> T:
        spec = self._lookup(key, tag)
        return self._resolve_sync(spec)  # pyright: ignore[reportReturnType]

    def _lookup(self, key: object, tag: str | None) -> ProviderSpec:
        if not _is_provider_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        spec = self._plan.by_key.get((key, tag))
        if spec is None:
            raise MissingProviderError(f'no provider for {key!r} (tag={tag!r})')
        return spec

    def _resolve_sync(self, spec: ProviderSpec) -> object:
        if spec.needs_async:
            raise AsyncInSyncContextError(
                f'{spec.key!r} requires async resolution; call aresolve() instead'
            )
        if spec.scope is Scope.SINGLETON:
            if spec in self._root:
                return self._root.get(spec)
            value = self._construct_sync(spec)
            self._root.put(spec, value)
            return value
        if spec.scope is Scope.TRANSIENT:
            return self._construct_sync(spec)
        raise NotImplementedError('scoped resolution not yet implemented')

    def _construct_sync(self, spec: ProviderSpec) -> object:
        if spec.shape is ProviderShape.VALUE:
            return spec.source
        kwargs = self._resolve_params_sync(spec)
        source = spec.source
        if spec.shape is ProviderShape.CLASS:
            assert isinstance(source, type)
            return source(**kwargs)
        if spec.shape is ProviderShape.FUNCTION:
            assert callable(source)
            return source(**kwargs)
        raise NotImplementedError(f'{spec.shape} sync construction not yet implemented')

    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        for param in spec.params:
            dep = self._plan.by_key.get((param.key, param.tag))
            if dep is None:
                if param.has_default:
                    continue
                raise MissingProviderError(
                    f"missing provider for parameter '{param.name}' of {spec.key!r}"
                )
            out[param.name] = self._resolve_sync(dep)
        return out


def _is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type) or is_object_token(value) or isinstance(value, str)
