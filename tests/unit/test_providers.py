"""Spec building: how a binding record becomes a provider key, shape and parameters."""

from collections.abc import AsyncGenerator, Callable, Generator, Iterator
from contextlib import contextmanager
from typing import Annotated, Literal

import pytest

from depin._core.graph import build_plan
from depin._core.introspect import AnnotatedMeta
from depin._core.markers import Tag, Token, provides
from depin._core.providers import as_provider_key, build_specs, param_key_from_meta, unwrap_container_type
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord, FrameBinding, ProviderShape, ValueBinding, fmt_key
from depin.errors import InvalidProviderError, InvalidScopeError


def test_build_specs_for_simple_class() -> None:
    class A: ...

    r = Registry().bind(A, scope=Scope.SINGLETON)
    specs = build_specs(r.records())

    assert len(specs) == 1
    spec = specs[0]
    assert spec.key is A
    assert spec.scope is Scope.SINGLETON
    assert spec.shape is ProviderShape.CLASS
    assert spec.tag is None
    assert spec.needs_async is False


def test_build_specs_resolves_provides_attribute() -> None:
    class Logger: ...

    @provides(Logger)
    class StdLogger(Logger): ...

    r = Registry().bind(StdLogger, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    assert spec.key is Logger


def test_build_specs_resolves_explicit_provides_kwarg() -> None:
    class Cache: ...

    class Redis(Cache): ...

    r = Registry().bind(Redis, provides=Cache, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    assert spec.key is Cache


def test_build_specs_value_record_emits_value_shape() -> None:
    tok = Token[int]('x')
    r = Registry().value(tok, 42)
    [spec] = list(build_specs(r.records()))
    assert spec.key == tok
    assert spec.shape is ProviderShape.VALUE
    assert spec.source == 42
    assert spec.scope is Scope.SINGLETON
    assert spec.needs_async is False
    assert spec.params == ()


def test_build_specs_value_record_preserves_its_tag() -> None:
    token = Token[int]('x')
    record = BindRecord(source=ValueBinding(token, 42), scope=Scope.SINGLETON, provides=None, tag='chosen')

    [spec] = list(build_specs((record,)))

    assert spec.tag == 'chosen'


def test_build_specs_scope_value_preserves_its_registration_details() -> None:
    token = Token[int]('request.id')
    [spec] = list(build_specs(Registry().scope_value(token, tag='request').records()))
    assert spec.key == token
    assert spec.tag == 'request'
    assert isinstance(spec.source, FrameBinding)
    assert spec.scope is Scope.SCOPED
    assert spec.shape is ProviderShape.FRAME
    assert spec.needs_async is False
    assert spec.params == ()


def test_generator_in_transient_rejected() -> None:
    def gen() -> Iterator[int]:
        yield 0

    r = Registry().bind(gen, scope=Scope.TRANSIENT)
    with pytest.raises(InvalidScopeError, match='owns a teardown') as exc:
        _ = build_specs(r.records())
    assert 'Use Scope.SINGLETON or Scope.SCOPED' in str(exc.value)


def test_generator_in_transient_explains_its_teardown_contract() -> None:
    def gen() -> Iterator[int]:
        yield 0

    with pytest.raises(InvalidScopeError) as exc:
        _ = build_specs(Registry().bind(gen, scope=Scope.TRANSIENT).records())
    assert 'provider owns a teardown, and a transient value is never cached, so nothing would drain it.' in str(
        exc.value
    )


def test_param_specs_extracted_from_init() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    r = Registry().bind(A, scope=Scope.SINGLETON).bind(B, scope=Scope.SINGLETON)
    specs = build_specs(r.records())
    by_key = {spec.key: spec for spec in specs}

    assert by_key[B].params[0].name == 'a'
    assert by_key[B].params[0].key is A


def test_param_specs_skip_self_and_var() -> None:
    class A:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

    r = Registry().bind(A, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    assert spec.params == ()


def test_param_specs_skip_cls_and_continue_after_variadic_parameters() -> None:
    class Dependency: ...

    def factory(cls: object, *values: object, dependency: Dependency) -> int:
        del cls, values, dependency
        return 1

    [factory_spec] = [
        candidate
        for candidate in build_specs(Registry().bind(Dependency).bind(factory).records())
        if candidate.key is int
    ]
    assert [(param.name, param.key) for param in factory_spec.params] == [('dependency', Dependency)]


def test_param_specs_continue_after_an_unannotated_default() -> None:
    def factory(optional: int = 1, *, required: int) -> int:
        return required

    del factory.__annotations__['optional']
    [spec] = list(build_specs(Registry().bind(factory, provides=int).records()))

    assert [(param.name, param.has_default) for param in spec.params] == [('optional', True), ('required', False)]


def test_param_spec_uses_default_when_no_provider_marker() -> None:
    class A:
        def __init__(self, value: int = 7) -> None:
            self.value = value

    r = Registry().bind(A, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    [p] = spec.params
    assert p.has_default is True
    assert p.default == 7


def test_param_spec_picks_token_from_annotated() -> None:
    tok = Token[str]('db.url')

    def factory(url: Annotated[str, tok]) -> int:
        return len(url)

    r = Registry().bind(factory, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    [p] = spec.params
    assert p.key == tok


def test_param_spec_picks_tag() -> None:
    class Cache: ...

    def factory(c: Annotated[Cache, Tag('primary')]) -> int:
        return 0

    r = Registry().bind(factory, scope=Scope.SINGLETON, provides=int)
    [spec] = list(build_specs(r.records()))
    [p] = spec.params
    assert p.tag == 'primary'
    assert p.key is Cache


def test_factory_without_return_annotation_is_rejected() -> None:
    def make():  # type: ignore[no-untyped-def]  # pyright: ignore[reportUnknownParameterType,reportMissingReturnType]
        return 1

    r = Registry().bind(make, scope=Scope.SINGLETON)  # pyright: ignore[reportUnknownArgumentType]
    with pytest.raises(InvalidProviderError, match='cannot infer the provider key'):
        _ = build_specs(r.records())


def test_non_callable_source_is_rejected() -> None:
    r = Registry().bind(42, scope=Scope.SINGLETON)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='cannot determine how to call'):
        _ = build_specs(r.records())


def test_parameter_without_annotation_or_default_is_rejected() -> None:
    class A:
        # `x` intentionally lacks an annotation — exercises the missing-annotation guard.
        def __init__(self, x) -> None:  # type: ignore[no-untyped-def]  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
            self.x = x

    r = Registry().bind(A, scope=Scope.SINGLETON)
    with pytest.raises(InvalidProviderError, match='no type annotation and no default') as exc:
        _ = build_specs(r.records())
    assert 'so depin cannot tell what to inject' in str(exc.value)


def test_async_factory_key_unwraps_the_coroutine_return() -> None:
    async def make() -> int:
        return 0

    r = Registry().bind(make, scope=Scope.SINGLETON, provides=int)
    [spec] = list(build_specs(r.records()))
    assert spec.key is int


def test_generator_factory_key_unwraps_the_yield_type() -> None:
    def make() -> Generator[int]:
        yield 0

    r = Registry().bind(make, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    assert spec.key is int


def test_async_generator_factory_key_unwraps_the_yield_type() -> None:
    async def make() -> AsyncGenerator[int]:
        yield 0

    r = Registry().bind(make, scope=Scope.SINGLETON)
    [spec] = list(build_specs(r.records()))
    assert spec.key is int
    assert spec.shape is ProviderShape.ASYNC_GENERATOR


def test_an_async_factory_is_keyed_by_its_whole_return_annotation() -> None:
    class Handler: ...

    async def make() -> list[Handler]:
        return []

    plan = build_plan(Registry().bind(make).records())
    assert [spec.key for spec in plan.order] == [list[Handler]]


def test_an_async_factory_returning_a_generic_keeps_its_parameter() -> None:
    class User: ...

    class Repo[T]: ...

    async def make() -> Repo[User]:
        return Repo()

    plan = build_plan(Registry().bind(make).records())
    assert [spec.key for spec in plan.order] == [Repo[User]]


def test_a_generator_factory_still_unwraps_its_container() -> None:
    class Conn: ...

    def connect() -> Generator[Conn]:
        yield Conn()

    plan = build_plan(Registry().bind(connect).records())
    assert [spec.key for spec in plan.order] == [Conn]


def test_a_context_manager_factory_still_unwraps_its_container() -> None:
    class Conn: ...

    @contextmanager
    def connect() -> Generator[Conn]:
        yield Conn()

    plan = build_plan(Registry().bind(connect).records())
    assert [spec.key for spec in plan.order] == [Conn]


def test_an_async_generator_factory_still_unwraps_its_container() -> None:
    class Conn: ...

    async def connect() -> AsyncGenerator[Conn]:
        yield Conn()

    plan = build_plan(Registry().bind(connect).records())
    assert [spec.key for spec in plan.order] == [Conn]


def test_forward_references_between_bound_classes_resolve_for_key_and_parameters() -> None:
    class Consumer:
        def __init__(self, dependency: 'Dependency') -> None: ...

    class Dependency: ...

    specs = build_specs(Registry().bind(Consumer).bind(Dependency).records())
    consumer = next(spec for spec in specs if spec.key is Consumer)
    assert consumer.params[0].key is Dependency


def test_forward_reference_return_annotation_resolves_against_bound_classes() -> None:
    class Produced: ...

    def make() -> 'Produced':
        return Produced()

    spec = next(spec for spec in build_specs(Registry().bind(Produced).bind(make).records()) if spec.source is make)
    assert spec.key is Produced


def test_forward_reference_resolves_a_class_registered_only_as_an_alias_key() -> None:
    class Store: ...

    def make(dep: 'Store') -> int:
        del dep
        return 0

    r = Registry().alias(Store, to=int).bind(make, provides=int)
    spec = next(spec for spec in build_specs(r.records()) if spec.source is make)
    assert spec.params[0].key is Store


def test_forward_reference_resolves_a_class_registered_only_as_an_alias_target() -> None:
    class Impl: ...

    def make(dep: 'Impl') -> int:
        del dep
        return 0

    r = Registry().alias('legacy', to=Impl).bind(make, provides=int)
    spec = next(spec for spec in build_specs(r.records()) if spec.source is make)
    assert spec.params[0].key is Impl


def test_forward_reference_resolves_a_class_registered_only_as_a_scope_value_key() -> None:
    class Principal: ...

    def make(dep: 'Principal') -> int:
        del dep
        return 0

    r = Registry().scope_value(Principal).bind(make, provides=int)
    spec = next(spec for spec in build_specs(r.records()) if spec.source is make)
    assert spec.params[0].key is Principal


def test_forward_reference_resolves_a_class_registered_only_as_a_collection_element() -> None:
    class Handler: ...

    def make(dep: 'Handler') -> int:
        del dep
        return 0

    r = Registry().collect(Handler, []).bind(make, provides=int)
    spec = next(spec for spec in build_specs(r.records()) if spec.source is make)
    assert spec.params[0].key is Handler


def test_forward_reference_resolves_a_class_registered_only_as_a_collection_member() -> None:
    class Impl: ...

    def make(dep: 'Impl') -> int:
        del dep
        return 0

    r = Registry().collect('handlers', [Impl]).bind(make, provides=int)
    spec = next(spec for spec in build_specs(r.records()) if spec.source is make)
    assert spec.params[0].key is Impl


@pytest.mark.parametrize('key', [int, 'legacy', Token[int]('k')])
def test_as_provider_key_accepts_classes_strings_and_tokens(key: object) -> None:
    assert as_provider_key(key) == key


def test_as_provider_key_rejects_anything_else() -> None:
    with pytest.raises(
        InvalidProviderError, match='a key must be a class, a Token, a string, or a parameterised generic'
    ):
        _ = as_provider_key(42)


@pytest.mark.parametrize('value', [Callable[[int], str], tuple[int, ...], Literal['a']])
def test_as_provider_key_catch_all_message_names_what_is_accepted(value: object) -> None:
    """Pins the message a reader gets for a `Callable`, a variadic `tuple`, or a `Literal` key."""
    with pytest.raises(InvalidProviderError, match='parameterised generic built by subscripting its origin'):
        _ = as_provider_key(value)


def test_as_provider_key_rejects_an_optional_union_outside_parameter_position() -> None:
    class Cache: ...

    with pytest.raises(InvalidProviderError, match="a provider's parameter, and this is not one") as exc:
        _ = as_provider_key(Cache | None)
    assert f'Use {Cache.__qualname__} directly' in str(exc.value)


def test_as_provider_key_still_rejects_a_union_of_two_or_more_providers() -> None:
    class Cache: ...

    class Logger: ...

    with pytest.raises(InvalidProviderError, match='names no single key'):
        _ = as_provider_key(Cache | Logger)


@pytest.mark.parametrize('annotation', [int, 42])
def test_unwrap_container_type_returns_none_without_a_generic_origin(annotation: object) -> None:
    assert unwrap_container_type(annotation) is None


def test_param_key_from_meta_prefers_a_named_token_over_the_base_type() -> None:
    tok: Token[int] = Token[int]('k')
    meta = AnnotatedMeta(base=int, token=None, tag=None, named=tok, optional=False)
    assert param_key_from_meta(meta) == tok


def test_fmt_key_renders_a_token_by_its_name() -> None:
    assert "Token('k')" in fmt_key(Token[int]('k'))


def test_fmt_key_renders_a_class_by_its_qualname() -> None:
    class Sample: ...

    assert fmt_key(Sample).endswith('Sample')


def test_a_builtin_without_an_inspectable_signature_declares_no_parameters() -> None:
    """`inspect.signature` refuses some C callables; such a provider simply takes nothing."""
    r = Registry().bind(min, scope=Scope.SINGLETON, provides=int)  # pyright: ignore[reportArgumentType]
    [spec] = list(build_specs(r.records()))
    assert spec.params == ()


def test_an_unannotated_parameter_with_a_default_is_left_to_the_callable() -> None:
    def make(retries=3) -> int:  # type: ignore[no-untyped-def]  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        return retries  # type: ignore[no-any-return]  # pyright: ignore[reportUnknownVariableType]

    r = Registry().bind(make, scope=Scope.SINGLETON, provides=int)  # pyright: ignore[reportUnknownArgumentType]
    [spec] = list(build_specs(r.records()))
    [param] = spec.params
    assert param.has_default
    assert param.default == 3
    assert param.name == 'retries'
    assert param.key is object


def test_an_unresolvable_annotation_is_reported_as_such() -> None:
    """The message must not claim the annotation is missing when it is merely unresolvable."""

    def make(dep: 'NeverDefined') -> int:  # type: ignore[name-defined]  # noqa: F821  # pyright: ignore[reportUndefinedVariable,reportUnknownParameterType]
        del dep
        return 1

    r = Registry().bind(make, scope=Scope.SINGLETON, provides=int)  # pyright: ignore[reportUnknownArgumentType]
    with pytest.raises(InvalidProviderError, match='could not be resolved') as exc:
        _ = build_specs(r.records())
    assert 'so depin can resolve the forward reference.' in str(exc.value)
