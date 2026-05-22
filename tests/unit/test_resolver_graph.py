from collections.abc import Iterator
from typing import Annotated

import pytest

from depin._core.markers import Tag, Token, provides
from depin._core.registry import Registry
from depin._core.resolver import build_specs
from depin._core.scope import Scope
from depin._core.spec import ProviderShape


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
    assert spec.key is tok
    assert spec.shape is ProviderShape.VALUE


def test_generator_in_transient_rejected() -> None:
    def gen() -> Iterator[int]:
        yield 0

    r = Registry().bind(gen, scope=Scope.TRANSIENT)
    with pytest.raises(ValueError, match='generator.*transient'):
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
    assert p.key is tok


def test_param_spec_picks_tag() -> None:
    class Cache: ...

    def factory(c: Annotated[Cache, Tag('primary')]) -> int:
        return 0

    r = Registry().bind(factory, scope=Scope.SINGLETON, provides=int)
    [spec] = list(build_specs(r.records()))
    [p] = spec.params
    assert p.tag == 'primary'
    assert p.key is Cache
