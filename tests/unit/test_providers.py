"""Spec building: how a binding record becomes a provider key, shape and parameters."""

from collections.abc import AsyncGenerator, Generator, Iterator
from typing import Annotated

import pytest

from depin._core.introspect import AnnotatedMeta
from depin._core.markers import Tag, Token, provides
from depin._core.providers import as_provider_key, build_specs, param_key_from_meta, unwrap_container_type
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import ProviderShape, fmt_key
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


def test_generator_in_transient_rejected() -> None:
    def gen() -> Iterator[int]:
        yield 0

    r = Registry().bind(gen, scope=Scope.TRANSIENT)
    with pytest.raises(InvalidScopeError, match='transient'):
        _ = build_specs(r.records())


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
    def make():  # pyright: ignore[reportUnknownParameterType,reportMissingReturnType]
        return 1

    r = Registry().bind(make, scope=Scope.SINGLETON)  # pyright: ignore[reportUnknownArgumentType]
    with pytest.raises(InvalidProviderError, match='cannot infer the provider key'):
        _ = build_specs(r.records())


def test_non_callable_source_is_rejected() -> None:
    r = Registry().bind(42, scope=Scope.SINGLETON)  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='cannot determine how to call'):
        _ = build_specs(r.records())


def test_parameter_without_annotation_or_default_is_rejected() -> None:
    class A:
        # `x` intentionally lacks an annotation — exercises the missing-annotation guard.
        def __init__(self, x) -> None:  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
            self.x = x

    r = Registry().bind(A, scope=Scope.SINGLETON)
    with pytest.raises(InvalidProviderError, match='no type annotation and no default'):
        _ = build_specs(r.records())


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


@pytest.mark.parametrize('key', [int, 'legacy', Token[int]('k')])
def test_as_provider_key_accepts_classes_strings_and_tokens(key: object) -> None:
    assert as_provider_key(key) == key


def test_as_provider_key_rejects_anything_else() -> None:
    with pytest.raises(InvalidProviderError, match='a key must be a class, a Token, or a string'):
        _ = as_provider_key(42)


@pytest.mark.parametrize('annotation', [int, 42])
def test_unwrap_container_type_returns_none_without_a_generic_origin(annotation: object) -> None:
    assert unwrap_container_type(annotation) is None


def test_param_key_from_meta_prefers_a_named_token_over_the_base_type() -> None:
    tok: Token[int] = Token[int]('k')
    meta = AnnotatedMeta(base=int, token=None, tag=None, named=tok)
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
    def make(retries=3) -> int:  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        return retries  # pyright: ignore[reportUnknownVariableType]

    r = Registry().bind(make, scope=Scope.SINGLETON, provides=int)  # pyright: ignore[reportUnknownArgumentType]
    [spec] = list(build_specs(r.records()))
    [param] = spec.params
    assert param.has_default
    assert param.default == 3


def test_an_unresolvable_annotation_is_reported_as_such() -> None:
    """The message must not claim the annotation is missing when it is merely unresolvable."""

    def make(dep: 'NeverDefined') -> int:  # noqa: F821  # pyright: ignore[reportUndefinedVariable,reportUnknownParameterType]
        del dep
        return 1

    r = Registry().bind(make, scope=Scope.SINGLETON, provides=int)  # pyright: ignore[reportUnknownArgumentType]
    with pytest.raises(InvalidProviderError, match='could not be resolved'):
        _ = build_specs(r.records())
