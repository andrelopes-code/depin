"""Turns a `BindRecord` into a `ProviderSpec`: infers the key, shape and parameters."""

import inspect
from collections.abc import Iterable
from typing import get_args, get_origin, get_type_hints

from depin._core.introspect import AnnotatedMeta, detect_shape, extract_annotated_meta, is_object_token
from depin._core.markers import get_provides
from depin._core.scope import Scope
from depin._core.spec import (
    ALIAS_PARAM,
    BindRecord,
    CollectionBinding,
    Ident,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    SpecSet,
    collection_key,
    collection_param,
    fmt_key,
    is_alias_binding,
    is_collection_binding,
    is_frame_binding,
    is_value_binding,
)
from depin._core.typeguards import (
    as_class,
    as_factory,
    invalid_key_error,
    is_parameterised_generic,
    is_provider_key,
)
from depin.errors import DuplicateProviderError, InvalidProviderError, InvalidScopeError

LIFECYCLE_SHAPES = frozenset(
    {
        ProviderShape.GENERATOR,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.CONTEXT_MANAGER,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)

ASYNC_SHAPES = frozenset(
    {
        ProviderShape.ASYNC_FUNCTION,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)

# ASYNC_FUNCTION is deliberately absent: `async def f() -> X` already means the
# awaited value is `X`, so there is nothing to unwrap. `Generator[X]` and its
# kin name a container around the value, which is what the other four shapes unwrap.
_UNWRAP_SHAPES = frozenset(
    {
        ProviderShape.GENERATOR,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.CONTEXT_MANAGER,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)


def build_specs(records: Iterable[BindRecord]) -> SpecSet:
    """Convert every active record into a spec, resolving forward references between them.

    A record whose condition does not hold is dropped before anything reads its
    shape or its annotations, which is what makes `when` usable on a binding
    that cannot be introspected in the deployment that switches it off.
    """
    active, inactive = _partition(records)
    localns = _registered_classes(active)
    return SpecSet(
        providers=tuple(_record_to_spec(rec, localns) for rec in active),
        inactive=frozenset(_inactive_idents(inactive, localns)),
    )


def _partition(records: Iterable[BindRecord]) -> tuple[tuple[BindRecord, ...], tuple[BindRecord, ...]]:
    active: list[BindRecord] = []
    inactive: list[BindRecord] = []
    for rec in records:
        target = active if is_active(rec) else inactive
        target.append(rec)
    return tuple(active), tuple(inactive)


def is_active(rec: BindRecord) -> bool:
    """Whether a record's condition admits it into the plan.

    Raises:
        InvalidProviderError: The condition is neither a bool nor a callable.
    """
    # Annotated `object` rather than `Condition | None`: the guard has to reject
    # a value an untyped caller passed, and a checker that trusts the annotation
    # reads the final branch as unreachable.
    condition: object = rec.condition
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    if callable(condition):
        return bool(condition())
    raise InvalidProviderError(
        f'cannot use {condition!r} as a binding condition: `when` takes a bool, or a callable '
        'of no arguments returning one, which depin calls inside freeze().'
    )


def _inactive_idents(records: Iterable[BindRecord], localns: dict[str, object]) -> Iterable[Ident]:
    # Filled in by Task 2, which needs the key-resolution machinery below to
    # name an inactive record's identity without introspecting its source.
    return ()


def _registered_classes(records: Iterable[BindRecord]) -> dict[str, object]:
    """Namespace of every class reachable from a record, in whatever role it plays, so a forward reference resolves."""
    out: dict[str, object] = {}
    for rec in records:
        for cls in _classes_reachable_from(rec):
            out[cls.__name__] = cls
    return out


def _classes_reachable_from(rec: BindRecord) -> tuple[type[object], ...]:
    """Every class a record names, in whatever role: source, `provides=`, marker key, target, element, or member.

    A `Token` and a string have no `__name__` to key the namespace by, so
    neither contributes. A parameterised generic contributes the classes inside
    it, so a class named only as `Repo[User]`'s argument still enters.
    """
    source = rec.source
    candidates: tuple[object, ...] = (source, rec.provides)
    if is_frame_binding(source):
        candidates += (source.key,)
    elif is_alias_binding(source):
        candidates += (source.key, source.target)
    elif is_collection_binding(source):
        candidates += (source.element, *source.members)
    return tuple(cls for candidate in candidates for cls in _classes_within(candidate))


def _classes_within(value: object) -> tuple[type[object], ...]:
    if isinstance(value, type):
        return (value,)
    if is_parameterised_generic(value):
        return tuple(cls for argument in get_args(value) for cls in _classes_within(argument))
    return ()


def _record_to_spec(rec: BindRecord, localns: dict[str, object]) -> ProviderSpec:
    if is_value_binding(rec.source):
        binding = rec.source
        return ProviderSpec(
            key=binding.token,
            tag=rec.tag,
            source=binding.value,
            scope=rec.scope,
            shape=ProviderShape.VALUE,
            needs_async=False,
            params=(),
        )

    if is_frame_binding(rec.source):
        frame = rec.source
        return ProviderSpec(
            key=as_provider_key(frame.key),
            tag=rec.tag,
            source=frame,
            scope=rec.scope,
            shape=ProviderShape.FRAME,
            needs_async=False,
            params=(),
        )

    if is_alias_binding(rec.source):
        alias = rec.source
        return ProviderSpec(
            key=as_provider_key(alias.key),
            tag=rec.tag,
            source=alias,
            scope=rec.scope,
            shape=ProviderShape.ALIAS,
            needs_async=False,
            params=(
                ParamSpec(
                    name=ALIAS_PARAM,
                    key=as_provider_key(alias.target),
                    tag=alias.target_tag,
                    has_default=False,
                    default=None,
                ),
            ),
        )

    if is_collection_binding(rec.source):
        collection = rec.source
        _reject_repeated_members(collection)
        return ProviderSpec(
            key=collection_key(as_provider_key(collection.element)),
            tag=rec.tag,
            source=collection,
            scope=rec.scope,
            shape=ProviderShape.COLLECTION,
            needs_async=False,
            params=tuple(
                ParamSpec(
                    name=collection_param(index),
                    key=as_provider_key(member),
                    tag=None,
                    has_default=False,
                    default=None,
                )
                for index, member in enumerate(collection.members)
            ),
        )

    source = rec.source
    shape = detect_shape(source)

    if shape in LIFECYCLE_SHAPES and rec.scope is Scope.TRANSIENT:
        raise InvalidScopeError(
            f'cannot bind {source!r} as transient: a generator or context-manager provider '
            'owns a teardown, and a transient value is never cached, so nothing would drain it. '
            'Use Scope.SINGLETON or Scope.SCOPED.'
        )

    return ProviderSpec(
        key=_resolve_key(source, rec.provides, shape, localns),
        tag=rec.tag,
        source=source,
        scope=rec.scope,
        shape=shape,
        needs_async=False,
        params=_extract_params(source, shape, localns),
    )


def _reject_repeated_members(collection: CollectionBinding) -> None:
    seen: set[ProviderKey] = set()
    for member in collection.members:
        if member in seen:
            raise DuplicateProviderError(
                f'{fmt_key(member)} is listed twice in the collection for {fmt_key(collection.element)}: '
                'a member resolves to one value, so listing it again only repeats that value. Remove the duplicate.'
            )
        seen.add(member)


def _resolve_key(
    source: object,
    explicit: type[object] | None,
    shape: ProviderShape,
    localns: dict[str, object],
) -> ProviderKey:
    if explicit is not None:
        return as_provider_key(explicit)
    if isinstance(source, type):
        attr = get_provides(source)
        return attr if attr is not None else source
    hints = _safe_type_hints(source, localns)
    ret = hints.get('return')
    if ret is None:
        raise _uninferrable_key_error(source)
    if shape in _UNWRAP_SHAPES:
        unwrapped = unwrap_container_type(ret)
        if unwrapped is not None:
            return unwrapped
    return as_provider_key(ret)


def _uninferrable_key_error(source: object) -> InvalidProviderError:
    """Why a factory's key could not be read off its return annotation.

    A factory that declares no return annotation and one whose annotations name
    something unresolvable both reach `_resolve_key` with no hints, and the
    advice differs: the first needs an annotation, the second needs the name it
    already wrote to be resolvable.
    """
    if 'return' in inspect.get_annotations(as_factory(source, source)):
        return InvalidProviderError(
            f'cannot infer the provider key for {source!r}: it declares a return annotation, but an '
            'annotation on it could not be resolved. Import the name at module level, or register '
            'the class in any role, so depin can resolve the forward reference — or pass '
            'provides=... to name the key directly.'
        )
    return InvalidProviderError(
        f'cannot infer the provider key for {source!r}: add a return type annotation, or pass provides=...'
    )


def unwrap_container_type(annotation: object) -> ProviderKey | None:
    """Read ``T`` out of ``Generator[T]``, ``AsyncIterator[T]``, ``Awaitable[T]``, and friends."""
    if get_origin(annotation) is None:
        return None
    args = get_args(annotation)
    if not args:
        return None
    return as_provider_key(args[0])


def as_provider_key(value: object) -> ProviderKey:
    if is_provider_key(value):
        return value
    raise invalid_key_error(value)


def _extract_params(source: object, shape: ProviderShape, localns: dict[str, object]) -> tuple[ParamSpec, ...]:
    target = as_class(source, source).__init__ if shape is ProviderShape.CLASS else as_factory(source, source)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        # `inspect.signature` rejects some C-implemented callables outright;
        # such a provider simply declares no injectable parameters.
        return ()

    hints = _safe_type_hints(target, localns)

    params: list[ParamSpec] = []
    for name, param in sig.parameters.items():
        if name in ('self', 'cls'):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        raw_annotation = hints.get(name)
        if raw_annotation is None:
            if param.annotation is not inspect.Parameter.empty:
                raise InvalidProviderError(
                    f"the annotation on parameter '{name}' of {source!r} could not be resolved "
                    f'({param.annotation!r}). Import the name at module level, or register it in any '
                    'role, so depin can resolve the forward reference.'
                )
            if param.default is inspect.Parameter.empty:
                raise InvalidProviderError(
                    f"parameter '{name}' of {source!r} has no type annotation and no default, "
                    'so depin cannot tell what to inject'
                )
            params.append(ParamSpec(name=name, key=object, tag=None, has_default=True, default=param.default))
            continue

        meta = extract_annotated_meta(raw_annotation)
        has_default = param.default is not inspect.Parameter.empty
        params.append(
            ParamSpec(
                name=name,
                key=param_key_from_meta(meta),
                tag=meta.tag,
                has_default=has_default,
                default=param.default if has_default else None,
                optional=meta.optional,
            )
        )

    return tuple(params)


def param_key_from_meta(meta: AnnotatedMeta) -> ProviderKey:
    if meta.token is not None:
        return meta.token
    if isinstance(meta.named, str):
        return meta.named
    if is_object_token(meta.named):
        return meta.named
    return as_provider_key(meta.base)


def _safe_type_hints(target: object, localns: dict[str, object]) -> dict[str, object]:
    """Resolve annotations, returning nothing when a name in them cannot be resolved.

    Callers decide what an empty result means: `_resolve_key` reports an
    un-inferrable provider key, `_extract_params` distinguishes a missing
    annotation from an unresolvable one.
    """
    try:
        return dict(get_type_hints(target, localns=localns, include_extras=True))
    except (NameError, TypeError):
        return {}
