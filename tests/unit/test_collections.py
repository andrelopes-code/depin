"""`Container.collect` gathers several providers under one `list[Element]` key."""

from collections.abc import Generator
from typing import Annotated, Protocol

import pytest

from depin import Container, ProviderShape, Registry, Scope, Tag
from depin.errors import DuplicateProviderError, MissingProviderError


class Handler(Protocol):
    def run(self) -> str: ...


class EmailHandler:
    def run(self) -> str:
        return 'email'


class SmsHandler:
    def run(self) -> str:
        return 'sms'


def _both() -> Container:
    return Container().bind(EmailHandler).bind(SmsHandler).collect(Handler, [EmailHandler, SmsHandler])


def test_a_collection_resolves_its_members_in_declaration_order() -> None:
    di = _both().freeze()
    assert [handler.run() for handler in di.resolve(list[Handler])] == ['email', 'sms']


def test_a_collection_holds_the_same_instances_as_direct_resolution() -> None:
    di = _both().freeze()
    first, second = di.resolve(list[Handler])
    assert first is di[EmailHandler]
    assert second is di[SmsHandler]


def test_a_collection_is_injected_into_a_provider() -> None:
    class Dispatcher:
        def __init__(self, handlers: list[Handler]) -> None:
            self.handlers = handlers

    di = _both().bind(Dispatcher).freeze()
    assert [handler.run() for handler in di[Dispatcher].handlers] == ['email', 'sms']


def test_each_resolution_returns_a_fresh_list_over_shared_members() -> None:
    di = _both().freeze()
    first = di.resolve(list[Handler])
    second = di.resolve(list[Handler])
    assert first is not second
    assert first[0] is second[0]


def test_an_empty_collection_resolves_to_an_empty_list() -> None:
    di = Container().collect(Handler, []).freeze()
    assert di.resolve(list[Handler]) == []


def test_a_collection_carries_its_own_tag() -> None:
    di = (
        Container()
        .bind(EmailHandler)
        .bind(SmsHandler)
        .collect(Handler, [EmailHandler], tag='fast')
        .collect(Handler, [SmsHandler], tag='slow')
        .freeze()
    )
    assert [h.run() for h in di.resolve(list[Handler], tag='fast')] == ['email']
    assert [h.run() for h in di.resolve(list[Handler], tag='slow')] == ['sms']


def test_a_tagged_collection_is_selected_by_annotation() -> None:
    class Dispatcher:
        def __init__(self, handlers: Annotated[list[Handler], Tag('fast')]) -> None:
            self.handlers = handlers

    di = Container().bind(EmailHandler).collect(Handler, [EmailHandler], tag='fast').bind(Dispatcher).freeze()
    assert [h.run() for h in di[Dispatcher].handlers] == ['email']


def test_a_collection_member_may_be_an_alias() -> None:
    di = Container().bind(EmailHandler).alias(Handler, to=EmailHandler).collect(Handler, [Handler]).freeze()
    assert di.resolve(list[Handler])[0] is di[EmailHandler]


def test_a_scoped_member_is_rebuilt_per_scope() -> None:
    di = Container().bind(EmailHandler, scope=Scope.SCOPED).collect(Handler, [EmailHandler], tag='scoped').freeze()
    with di.scope():
        first = di.resolve(list[Handler], tag='scoped')[0]
        assert di.resolve(list[Handler], tag='scoped')[0] is first
    with di.scope():
        assert di.resolve(list[Handler], tag='scoped')[0] is not first


def test_each_member_is_torn_down_once() -> None:
    events: list[str] = []

    class First: ...

    class Second: ...

    def first() -> Generator[First]:
        events.append('first open')
        yield First()
        events.append('first close')

    def second() -> Generator[Second]:
        events.append('second open')
        yield Second()
        events.append('second close')

    di = Container().bind(first).bind(second).collect(object, [First, Second]).freeze()
    _ = di.resolve(list[object])
    _ = di.resolve(list[object])
    di.close()
    assert events == ['first open', 'second open', 'second close', 'first close']


def test_a_collection_appears_in_the_graph_as_a_transient_node() -> None:
    node = _both().freeze().graph().node(list[Handler])
    assert node.shape is ProviderShape.COLLECTION
    assert node.scope is Scope.TRANSIENT
    assert [edge.parameter for edge in node.dependencies] == ['member_0', 'member_1']


def test_a_registry_carries_a_collection_into_a_container() -> None:
    registry = Registry('handlers').bind(EmailHandler).collect(Handler, [EmailHandler])
    di = Container(registry).freeze()
    assert di.resolve(list[Handler])[0] is di[EmailHandler]


def test_binding_two_implementations_under_one_key_still_raises() -> None:
    builder = (
        Container()
        .bind(EmailHandler, provides=Handler)
        .bind(SmsHandler, provides=Handler)
        .collect(Handler, [EmailHandler])
    )
    with pytest.raises(DuplicateProviderError):
        _ = builder.freeze()


def test_a_collection_over_an_unbound_member_is_rejected() -> None:
    with pytest.raises(MissingProviderError, match='EmailHandler'):
        _ = Container().collect(Handler, [EmailHandler]).freeze()


def test_a_member_listed_twice_in_one_collection_is_rejected() -> None:
    builder = Container().bind(EmailHandler).collect(Handler, [EmailHandler, EmailHandler])
    with pytest.raises(DuplicateProviderError, match=r'EmailHandler.*listed twice'):
        _ = builder.freeze()


def test_only_a_list_generic_is_registered_as_a_collection_key() -> None:
    """`collect` only ever builds a `list[Element]` key; any other generic is unbound, not rejected."""

    class User: ...

    class Repo[T]: ...

    di = _both().freeze()

    with pytest.raises(MissingProviderError, match='no provider for'):
        di.resolve(dict[str, int])
    with pytest.raises(MissingProviderError, match='no provider for'):
        di.resolve(Repo[User])
    with pytest.raises(MissingProviderError, match='no provider for'):
        di.resolve(set[Handler])
    assert di.explain(dict[str, int]).startswith('no provider for')
    assert di.explain(Repo[User]).startswith('no provider for')
    assert di.explain(set[Handler]).startswith('no provider for')

    assert [h.run() for h in di.resolve(list[Handler])] == ['email', 'sms']
