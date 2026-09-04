"""A parameterised generic is a provider key, distinguished by equality like any other."""

import typing
from collections.abc import Callable
from typing import Protocol

import pytest

from depin import Container, ProviderShape, Scope
from depin.errors import InvalidProviderError, MissingProviderError


class User: ...


class Order: ...


class Repo[T]:
    def __init__(self) -> None:
        self.rows: list[str] = []


class Reader[T](Protocol):
    def read(self) -> str: ...


def _user_repo() -> Repo[User]:
    return Repo()


def _order_repo() -> Repo[Order]:
    return Repo()


def test_two_parameterisations_are_two_bindings() -> None:
    di = Container().bind(_user_repo).bind(_order_repo).freeze()
    user_repo: object = di.resolve(Repo[User])
    order_repo: object = di.resolve(Repo[Order])
    assert user_repo is not order_repo


def test_a_parameterisation_is_distinct_from_the_bare_class() -> None:
    def bare() -> Repo[object]:
        return Repo()

    di = Container().bind(bare, provides=Repo).bind(_user_repo).freeze()
    assert di.resolve(Repo) is not di.resolve(Repo[User])


def test_a_generic_key_is_injected_by_annotation() -> None:
    class Service:
        def __init__(self, repo: Repo[User]) -> None:
            self.repo = repo

    di = Container().bind(_user_repo).bind(Service).freeze()
    assert di[Service].repo is di.resolve(Repo[User])


def test_a_generic_protocol_is_a_key() -> None:
    class MemReader:
        def read(self) -> str:
            return 'mem'

    di = Container().bind(MemReader, provides=Reader[User]).freeze()
    assert di.resolve(Reader[User]).read() == 'mem'


def test_a_generic_key_nests() -> None:
    def nested() -> Repo[Repo[User]]:
        return Repo()

    di = Container().bind(nested).freeze()
    assert di.graph().node(Repo[Repo[User]]).shape is ProviderShape.FUNCTION


def test_a_generic_key_works_as_an_alias_target() -> None:
    di = Container().bind(_user_repo).alias(Reader[User], to=Repo[User]).freeze()
    aliased: object = di.resolve(Reader[User])
    target: object = di.resolve(Repo[User])
    assert aliased is target


def test_a_generic_key_works_as_a_collection_element() -> None:
    di = Container().bind(_user_repo).bind(_order_repo).collect(Repo[User], [Repo[User], Repo[Order]]).freeze()
    assert len(di.resolve(list[Repo[User]])) == 2


def test_a_generic_key_is_scoped_like_any_other() -> None:
    di = Container().bind(_user_repo, scope=Scope.SCOPED).freeze()
    with di.scope():
        first = di.resolve(Repo[User])
        assert di.resolve(Repo[User]) is first
    with di.scope():
        assert di.resolve(Repo[User]) is not first


def test_a_parameterisation_does_not_satisfy_a_wider_one() -> None:
    class Service:
        def __init__(self, repo: Repo[object]) -> None:
            del repo

    with pytest.raises(MissingProviderError, match=r'Repo\[object\]'):
        _ = Container().bind(_user_repo).bind(Service).freeze()


@pytest.mark.parametrize(
    'annotation',
    [typing.List[User], typing.Dict[str, int], typing.Sequence[User]],  # noqa: UP006
)
def test_a_deprecated_typing_alias_is_rejected(annotation: object) -> None:
    with pytest.raises(InvalidProviderError, match='deprecated'):
        _ = Container().alias(annotation, to=User).freeze()  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_a_callable_key_is_rejected() -> None:
    with pytest.raises(InvalidProviderError, match='as a provider key'):
        _ = Container().alias(Callable[[int], str], to=User).freeze()  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def _users() -> list[User]:
    return []


@pytest.mark.parametrize(
    ('explicit', 'fragment'),
    [
        (42, 'a key must be a class'),
        (typing.List[User], 'deprecated typing alias'),  # noqa: UP006
        (User | None, 'and this is not one'),
        (Callable[[int], str], 'is not itself a provider key'),
        (tuple[User, ...], 'is not itself a provider key'),
    ],
)
def test_an_explicit_provides_is_validated_like_any_other_key(explicit: object, fragment: str) -> None:
    class Impl: ...

    with pytest.raises(InvalidProviderError, match=fragment):
        _ = Container().bind(Impl, provides=explicit).freeze()  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType]


def test_two_spellings_of_one_key_cannot_both_be_registered() -> None:
    """The failure mode the canonical-form rule exists to prevent: two nodes that print alike."""

    class Canonical: ...

    class Deprecated: ...

    builder = (
        Container()
        .bind(Canonical, provides=list[User])
        .bind(
            Deprecated,
            provides=typing.List[User],  # noqa: UP006
        )
    )
    with pytest.raises(InvalidProviderError, match='deprecated typing alias'):
        _ = builder.freeze()


@pytest.mark.parametrize('nested', [list[typing.List[User]], Repo[typing.List[User]]])  # noqa: UP006
def test_canonicity_is_enforced_inside_a_nested_key(nested: object) -> None:
    class Impl: ...

    with pytest.raises(InvalidProviderError, match='deprecated typing alias'):
        _ = Container().bind(Impl, provides=nested).freeze()  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType]


def test_two_spellings_of_a_nested_key_cannot_both_be_registered() -> None:
    class Canonical: ...

    class Deprecated: ...

    builder = (
        Container()
        .bind(Canonical, provides=list[list[User]])
        .bind(
            Deprecated,
            provides=list[typing.List[User]],  # noqa: UP006
        )
    )
    with pytest.raises(InvalidProviderError, match='deprecated typing alias'):
        _ = builder.freeze()


def test_a_deprecated_alias_is_refused_by_every_runtime_gate() -> None:
    """A key that is present must never be reported as missing because it was spelled the deprecated way."""
    di = Container().bind(_users).freeze()
    alias = typing.List[User]  # noqa: UP006
    assert di.resolve(list[User]) == []

    with pytest.raises(MissingProviderError, match='not a valid key type'):
        _ = di.resolve(alias)  # pyright: ignore[reportArgumentType]
    with pytest.raises(MissingProviderError, match='not a valid key type'):
        _ = di.explain(alias)  # pyright: ignore[reportArgumentType]
