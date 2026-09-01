import typing
from collections.abc import Callable, Sequence
from typing import Protocol

import pytest

from depin import Container
from depin._core.spec import ParamSpec, Underlying
from depin._core.typeguards import (
    as_alias_target,
    as_check,
    as_collection_members,
    invalid_key_error,
    is_canonical_generic,
    is_provider_key,
)
from depin.errors import InvalidProviderError


def test_the_canonical_generic_spellings_are_accepted() -> None:
    class User: ...

    class Repo[T]: ...

    class Reader[T](Protocol):
        def read(self) -> str: ...

    for key in (list[User], dict[str, int], Sequence[User], Repo[User], Reader[User], Repo[Repo[User]]):
        assert is_canonical_generic(key), key


def test_the_deprecated_typing_aliases_are_not_canonical() -> None:
    class User: ...

    for key in (typing.List[User], typing.Dict[str, int], typing.Sequence[User]):  # noqa: UP006
        assert not is_canonical_generic(key), key


def test_a_non_class_origin_is_not_canonical() -> None:
    """Called directly: `Literal['a']` never reaches the predicate through `is_generic_key`, which rejects it first."""
    assert not is_canonical_generic(typing.Literal['a'])


def test_an_underlying_key_is_a_provider_key() -> None:
    class Store: ...

    assert is_provider_key(Underlying(Store, 0))


def test_as_check_raises_for_a_non_callable_check() -> None:
    class Store: ...

    with pytest.raises(InvalidProviderError, match='is not callable'):
        _ = as_check(42, Store)


class Cache: ...


class Clock: ...


class Impl: ...


def _callable_factory() -> Callable[[int], str]:
    raise NotImplementedError


def _pairs_factory() -> dict[Callable[[int], str], tuple[Cache, ...]]:
    raise NotImplementedError


def _tuple_factory() -> tuple[Cache, ...]:
    raise NotImplementedError


def _optional_factory() -> Cache | None:
    raise NotImplementedError


def _union_factory() -> Cache | Clock:
    raise NotImplementedError


def _optional_union_factory() -> Cache | Clock | None:
    raise NotImplementedError


@pytest.mark.parametrize(('applied', 'layer'), [(0, 'undecorated'), (2, 'decorated x2')])
def test_an_underlying_key_is_refused_naming_the_key_the_decoration_wraps(applied: int, layer: str) -> None:
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = Container().bind(Cache).alias(Underlying(Cache, applied), to=Cache).freeze()

    assert str(excinfo.value) == (
        f'cannot register a binding under Cache ({layer}): Underlying names a layer of an existing '
        'decoration chain, constructed to inspect a graph, not to register one. Use Cache instead, '
        'the key the decoration wraps.'
    )


def test_a_deprecated_alias_nested_in_a_key_is_refused_naming_the_canonical_spelling() -> None:
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = Container().bind(Impl, provides=list[typing.Sequence[Cache]]).freeze()

    assert str(excinfo.value) == (
        'cannot use typing.Sequence[test_typeguards.Cache] as a provider key: it is the deprecated '
        'typing alias for Sequence[Cache], and a different object at runtime, so the two would be '
        'two keys that print alike. Write Sequence[Cache] instead, subscripting '
        'collections.abc.Sequence itself.'
    )


@pytest.mark.parametrize(
    ('factory', 'rendered', 'rejected'),
    [
        (_callable_factory, 'collections.abc.Callable[[int], str]', "[<class 'int'>]"),
        (_tuple_factory, 'tuple[test_typeguards.Cache, ...]', 'Ellipsis'),
        (
            _pairs_factory,
            'dict[collections.abc.Callable[[int], str], tuple[test_typeguards.Cache, ...]]',
            'collections.abc.Callable[[int], str], tuple[test_typeguards.Cache, ...]',
        ),
    ],
)
def test_a_parameterised_key_is_refused_naming_every_argument_that_is_no_key(
    factory: Callable[[], object], rendered: str, rejected: str
) -> None:
    """The third case carries two rejected arguments, so the message must list both, comma-separated."""
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = Container().bind(factory).freeze()

    assert str(excinfo.value) == (
        f'cannot use {rendered} as a provider key: its argument {rejected} is not itself a provider '
        'key, and every argument of a parameterised key must be one. That is why '
        'Callable[[int], str] and tuple[X, ...] are never keys.'
    )


def test_an_optional_key_is_refused_naming_the_single_key_it_wraps() -> None:
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = Container().bind(_optional_factory).freeze()

    assert str(excinfo.value) == (
        'cannot use test_typeguards.Cache | None as a provider key: depin reads `T | None` as an '
        "optional dependency only on a provider's parameter, and this is not one. Use Cache "
        'directly.'
    )


@pytest.mark.parametrize(
    ('factory', 'rendered'),
    [
        (_union_factory, 'test_typeguards.Cache | test_typeguards.Clock'),
        (_optional_union_factory, 'test_typeguards.Cache | test_typeguards.Clock | None'),
    ],
)
def test_a_union_of_two_or_more_providers_is_refused(factory: Callable[[], object], rendered: str) -> None:
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = Container().bind(factory).freeze()

    assert str(excinfo.value) == (
        f'cannot use {rendered} as a provider key: depin reads `T | None` as an optional '
        'dependency, but a union of two or more providers names no single key wherever it is used — '
        'as a parameter annotation, an alias target, or a collection element. Write the one key you '
        'mean instead, or, for a parameter, disambiguate with Annotated[..., Tag(...)].'
    )


@pytest.mark.parametrize('value', [42, None])
def test_a_value_of_no_key_kind_is_refused_with_the_shapes_a_key_may_take(value: object) -> None:
    """Called directly: every public gate rejects such a value statically, so only an untyped caller reaches it."""
    assert str(invalid_key_error(value)) == (
        f'cannot use {value!r} as a provider key: a key must be a class, a Token, a string, or a '
        'parameterised generic built by subscripting its origin, such as list[X] or Repo[X] '
        '(not the deprecated typing.List[X] form).'
    )


def test_an_alias_that_resolved_no_target_names_the_key() -> None:
    """Called directly: `freeze()` gives every alias one required parameter, so resolution cannot leave it unbound."""
    with pytest.raises(InvalidProviderError) as excinfo:
        _ = as_alias_target({}, Cache)

    assert str(excinfo.value) == 'alias for Cache resolved no target binding'


@pytest.mark.parametrize(('resolved', 'missing'), [((), 'first, second'), (('first',), 'second')])
def test_a_collection_missing_members_names_the_key_and_every_missing_member(
    resolved: tuple[str, ...], missing: str
) -> None:
    """Called directly for the reason `as_alias_target` is: every member is a required parameter."""
    params = (
        ParamSpec(name='first', key=Cache, tag=None, has_default=False, default=None),
        ParamSpec(name='second', key=Clock, tag=None, has_default=False, default=None),
    )
    kwargs: dict[str, object] = {name: Cache() for name in resolved}

    with pytest.raises(InvalidProviderError) as excinfo:
        _ = as_collection_members(kwargs, params, list[Cache])

    assert str(excinfo.value) == f'collection for list[Cache] resolved no value for {missing}'
