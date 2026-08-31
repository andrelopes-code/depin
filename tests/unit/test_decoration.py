"""Decoration: a wrapper node over a binding that keeps its own identity."""

import pytest

from depin import Container
from depin._core.providers import build_specs
from depin.errors import InvalidProviderError


def test_a_decorate_record_becomes_a_decoration_not_a_provider() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    specs = build_specs(Container().bind(Store).decorate(Store, Loud).records())
    assert len(specs.providers) == 1
    assert len(specs.decorations) == 1
    assert specs.decorations[0].key is Store
    assert specs.decorations[0].inner == 'inner'


def test_a_decorator_with_no_parameter_for_its_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self) -> None: ...

    container = Container().bind(Store).decorate(Store, Loud)
    with pytest.raises(InvalidProviderError, match='declares no parameter'):
        _ = container.freeze()


def test_a_decorator_with_two_parameters_for_its_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, first: Store, second: Store) -> None: ...

    container = Container().bind(Store).decorate(Store, Loud)
    with pytest.raises(InvalidProviderError, match='declares 2 parameters'):
        _ = container.freeze()


def test_a_tagged_decorator_matches_the_tagged_parameter() -> None:
    from typing import Annotated

    from depin import Tag

    class Store: ...

    class Loud:
        def __init__(self, inner: Annotated[Store, Tag('primary')]) -> None: ...

    specs = build_specs(Container().bind(Store, tag='primary').decorate(Store, Loud, tag='primary').records())
    assert specs.decorations[0].tag == 'primary'
    assert specs.decorations[0].inner == 'inner'


def test_an_inactive_decorator_is_not_reported_as_an_inactive_binding() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store).decorate(Store, Loud, when=False).freeze()
    assert 'registered but inactive' not in di.explain(Store)
