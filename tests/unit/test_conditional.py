"""Bindings under a predicate, decided inside `freeze()`."""

from collections.abc import Generator

import pytest

from depin import Container, Registry, Token
from depin.errors import InvalidProviderError, MissingProviderError


def test_a_binding_with_a_true_condition_is_registered() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=True).freeze()
    assert isinstance(di[Cache], Cache)


def test_a_binding_with_a_false_condition_is_absent() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=False).freeze()
    with pytest.raises(MissingProviderError):
        _ = di[Cache]


def test_an_inactive_binding_is_not_a_node_of_the_graph() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=False).freeze()
    assert di.graph().nodes == ()


def test_a_predicate_is_called_once_per_freeze() -> None:
    class Cache: ...

    calls: list[int] = []

    def predicate() -> bool:
        calls.append(1)
        return True

    container = Container().bind(Cache, when=predicate)
    _ = container.freeze()
    assert len(calls) == 1
    _ = container.freeze()
    assert len(calls) == 2


def test_a_predicate_is_not_called_before_freeze() -> None:
    class Cache: ...

    calls: list[int] = []

    def predicate() -> bool:
        calls.append(1)
        return True

    _ = Container().bind(Cache, when=predicate)
    assert calls == []


def test_two_bindings_for_one_key_are_switched_by_condition() -> None:
    class Store: ...

    class Postgres(Store): ...

    class Memory(Store): ...

    production = False
    di = (
        Container()
        .bind(Postgres, provides=Store, when=lambda: production)
        .bind(Memory, provides=Store, when=lambda: not production)
        .freeze()
    )
    assert isinstance(di.resolve(Store), Memory)


def test_an_inactive_binding_is_an_unsatisfied_dependency() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    with pytest.raises(MissingProviderError):
        _ = Container().bind(Cache, when=False).bind(Service).freeze()


def test_an_inactive_dependency_is_excused_by_a_default() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None = None) -> None:
            self.cache = cache

    di = Container().bind(Cache, when=False).bind(Service).freeze()
    assert di[Service].cache is None


def test_an_inactive_dependency_is_excused_by_an_optional_annotation() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Cache, when=False).bind(Service).freeze()
    assert di[Service].cache is None


def test_every_registration_method_takes_a_condition() -> None:
    class Store: ...

    class Handler: ...

    class Request: ...

    port = Token[int]('port')
    container = (
        Container()
        .bind(Store, when=False)
        .value(port, 1, when=False)
        .scope_value(Request, when=False)
        .alias(Handler, to=Store, when=False)
        .collect(Handler, [Store], when=False)
    )
    assert container.freeze().graph().nodes == ()


def test_a_scope_decorator_takes_a_condition() -> None:
    container = Container()

    @container.singleton(when=False)
    class Cache: ...

    @container.scoped(when=False)
    class Session: ...

    @container.transient(when=False)
    class Ticket: ...

    assert {rec.source for rec in container.records()} == {Cache, Session, Ticket}
    assert container.freeze().graph().nodes == ()


def test_a_registry_carries_conditions_into_a_container() -> None:
    class Cache: ...

    registry = Registry('infra').bind(Cache, when=False)
    assert Container(registry).freeze().graph().nodes == ()


def test_a_condition_that_is_neither_a_bool_nor_a_callable_is_rejected() -> None:
    class Cache: ...

    container = Container().bind(Cache, when=3)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='binding condition'):
        _ = container.freeze()


def test_an_inactive_binding_is_never_introspected() -> None:
    # `3` is neither a class nor a callable, so `detect_shape` would reject it.
    # Freezing proves the record never reached introspection at all.
    container = Container().bind(3, when=False)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert container.freeze().graph().nodes == ()


def test_a_missing_inactive_key_is_named_as_inactive() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    container = Container().bind(Cache, when=False).bind(Service)
    with pytest.raises(MissingProviderError) as error:
        _ = container.freeze()
    assert 'registered but inactive' in str(error.value)


def test_a_missing_key_with_no_inactive_binding_is_not_named_as_inactive() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    with pytest.raises(MissingProviderError) as error:
        _ = Container().bind(Service).freeze()
    assert 'registered but inactive' not in str(error.value)


def test_explain_and_freeze_report_an_inactive_key_alike() -> None:
    """`format_missing` is shared by `freeze()` and `explain()`, so the note about an inactive
    conditional binding is meant to appear identically in both. A required parameter that
    freeze() rejects can never itself sit in a frozen graph to ask `explain()` about, so the
    second consumer below gives its parameter a default: `_check_missing` then lets `freeze()`
    succeed, while `_deepest_requirement` still reports the chain the parameter would need if it
    were required. `fmt_key` renders a class by `__qualname__`, so the second consumer's
    `__qualname__` is set to match the first's, making the two captured lines comparable for
    exact equality.
    """

    class Cache: ...

    class RequiredConsumer:
        def __init__(self, cache: Cache) -> None: ...

    with pytest.raises(MissingProviderError) as error:
        _ = Container().bind(Cache, when=False).bind(RequiredConsumer).freeze()
    freeze_text = str(error.value)

    class DefaultedConsumer:
        def __init__(self, cache: Cache | None = None) -> None: ...

    DefaultedConsumer.__qualname__ = RequiredConsumer.__qualname__

    frozen = Container().bind(Cache, when=False).bind(DefaultedConsumer).freeze()
    explain_text = frozen.explain(Cache)

    print(freeze_text)
    print(explain_text)
    assert 'registered but inactive' in freeze_text
    assert freeze_text == explain_text


def test_an_inactive_factory_key_is_named_from_its_return_annotation() -> None:
    class Cache: ...

    def build_cache() -> Cache:
        return Cache()

    frozen = Container().bind(build_cache, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Cache)


def test_an_inactive_generator_factory_key_is_read_through_its_container_type() -> None:
    class Pool: ...

    def pool() -> Generator[Pool]:
        yield Pool()

    frozen = Container().bind(pool, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Pool)


def test_an_inactive_alias_key_is_named() -> None:
    class Store: ...

    class Reader: ...

    frozen = Container().bind(Store).alias(Reader, to=Store, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Reader)


def test_an_inactive_value_token_is_named() -> None:
    port = Token[int]('port')
    frozen = Container().value(port, 1, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(port)


def test_an_inactive_collection_key_is_named() -> None:
    class Handler: ...

    frozen = Container().collect(Handler, [], when=False).freeze()
    assert 'registered but inactive' in frozen.explain(list[Handler])
