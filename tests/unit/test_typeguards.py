import typing
from collections.abc import Sequence
from typing import Protocol

from depin._core.typeguards import is_canonical_generic


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
