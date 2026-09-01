"""Decoration: a wrapper node over a binding that keeps its own identity."""

from collections.abc import Generator
from typing import override

import pytest

from depin import Container, Named, ProviderShape, Scope, Tag, Token, Underlying
from depin._core.providers import build_specs
from depin.errors import AsyncInSyncContextError, InvalidProviderError, InvalidScopeError, MissingProviderError


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


def test_a_decorated_singleton_resolves_through_its_wrapper() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    assert di.resolve(Store).get() == 'PLAIN'


def test_a_decorated_singleton_keeps_one_identity() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    resolved = di.resolve(Store)
    assert resolved is di.resolve(Store)
    assert isinstance(resolved, Loud)


def test_the_undecorated_form_is_reachable_under_underlying() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    decorated = di.resolve(Store)
    assert isinstance(decorated, Loud)
    assert di.graph().node(Underlying(Store, 0)).shape is ProviderShape.CLASS


def test_a_consumer_receives_the_decorated_value() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    di = Container().bind(Store).bind(Service).decorate(Store, Loud).freeze()
    assert isinstance(di[Service].store, Loud)


def test_decorators_stack_in_registration_order() -> None:
    class Store:
        def get(self) -> str:
            return 'a'

    class Upper:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    class Bracket:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return f'[{self.inner.get()}]'

    di = Container().bind(Store).decorate(Store, Upper).decorate(Store, Bracket).freeze()
    assert di.resolve(Store).get() == '[A]'


def test_a_factory_decorator_is_accepted() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        @override
        def get(self) -> str:
            return self.inner.get().upper()

    def wrap(inner: Store) -> Store:
        return Loud(inner)

    di = Container().bind(Store).decorate(Store, wrap).freeze()
    assert di.resolve(Store).get() == 'PLAIN'


def test_a_decorator_resolves_its_own_dependencies() -> None:
    class Prefix:
        text = '>'

    class Store:
        def get(self) -> str:
            return 'a'

    class Loud:
        def __init__(self, inner: Store, prefix: Prefix) -> None:
            self.inner = inner
            self.prefix = prefix

        def get(self) -> str:
            return f'{self.prefix.text}{self.inner.get()}'

    di = Container().bind(Prefix).bind(Store).decorate(Store, Loud).freeze()
    assert di.resolve(Store).get() == '>a'


def test_a_decorated_scoped_binding_is_rebuilt_per_scope() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store, scope=Scope.SCOPED).decorate(Store, Loud).freeze()
    with di.scope():
        first = di.resolve(Store)
        assert di.resolve(Store) is first
        assert isinstance(first, Loud)
    with di.scope():
        second = di.resolve(Store)
        assert second is not first
        assert isinstance(second, Loud)


def test_a_decorated_transient_binding_is_rebuilt_per_resolution() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store, scope=Scope.TRANSIENT).decorate(Store, Loud).freeze()
    first = di.resolve(Store)
    second = di.resolve(Store)
    assert first is not second
    assert isinstance(first, Loud)
    assert isinstance(second, Loud)


def test_a_decorated_alias_resolves_through_the_wrapper() -> None:
    class Reader: ...

    class Store(Reader):
        def get(self) -> str:
            return 'plain'

    class Loud(Reader):
        def __init__(self, inner: Reader) -> None:
            self.inner = inner

    di = Container().bind(Store).alias(Reader, to=Store).decorate(Reader, Loud).freeze()
    assert isinstance(di.resolve(Reader), Loud)


def test_a_decorated_value_resolves_through_the_wrapper() -> None:
    from typing import Annotated

    port = Token[int]('port')

    def double(inner: Annotated[int, Named(port)]) -> int:
        return inner * 2

    di = Container().value(port, 21).decorate(port, double).freeze()
    assert di[port] == 42


def test_a_tagged_binding_is_decorated_under_its_tag() -> None:
    from typing import Annotated

    class Store:
        def get(self) -> str:
            return 'primary'

    class Loud(Store):
        def __init__(self, inner: Annotated[Store, Tag('primary')]) -> None:
            self.inner = inner

    di = Container().bind(Store, tag='primary').decorate(Store, Loud, tag='primary').freeze()
    assert isinstance(di.resolve(Store, tag='primary'), Loud)


def test_an_override_replaces_the_decorated_key_whole() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Fake(Store):
        @override
        def get(self) -> str:
            return 'fake'

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    with di.override(Store, Fake()):
        assert di.resolve(Store).get() == 'fake'
    assert isinstance(di.resolve(Store), Loud)


def test_a_decorated_collection_resolves_through_the_wrapper() -> None:
    class Handler: ...

    class Email(Handler): ...

    class Sms(Handler): ...

    def reversed_handlers(inner: list[Handler]) -> list[Handler]:
        return list(reversed(inner))

    di = (
        Container()
        .bind(Email)
        .bind(Sms)
        .collect(Handler, [Email, Sms])
        .decorate(list[Handler], reversed_handlers)
        .freeze()
    )
    assert [type(handler) for handler in di.resolve(list[Handler])] == [Sms, Email]


def test_a_decorated_provider_is_torn_down_once_in_its_undecorated_position() -> None:
    events: list[str] = []

    class Early: ...

    class Store: ...

    class Late:
        def __init__(self, store: Store, early: Early) -> None: ...

    def early() -> Generator[Early]:
        events.append('open early')
        yield Early()
        events.append('close early')

    def store(early: Early) -> Generator[Store]:
        events.append('open store')
        yield Store()
        events.append('close store')

    def late(store: Store, early: Early) -> Generator[Late]:
        events.append('open late')
        yield Late(store, early)
        events.append('close late')

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    undecorated = Container().bind(early).bind(store).bind(late).freeze()
    _ = undecorated[Late]
    undecorated.close()
    baseline = list(events)

    events.clear()
    decorated = Container().bind(early).bind(store).bind(late).decorate(Store, Loud).freeze()
    _ = decorated[Late]
    _ = decorated[Store]
    decorated.close()

    assert events == baseline
    assert events.count('close store') == 1


def test_a_decorator_that_owns_a_teardown_is_drained_before_what_it_wraps() -> None:
    events: list[str] = []

    class Store: ...

    def store() -> Generator[Store]:
        events.append('open store')
        yield Store()
        events.append('close store')

    def loud(inner: Store) -> Generator[Store]:
        events.append('open loud')
        yield inner
        events.append('close loud')

    di = Container().bind(store).decorate(Store, loud).freeze()
    _ = di[Store]
    di.close()
    assert events == ['open store', 'open loud', 'close loud', 'close store']


async def test_an_async_decorator_over_a_sync_binding_needs_aresolve() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        @override
        def get(self) -> str:
            return self.inner.get().upper()

    async def loud(inner: Store) -> Store:
        return Loud(inner)

    di = Container().bind(Store).decorate(Store, loud).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Store)
    assert (await di.aresolve(Store)).get() == 'PLAIN'


async def test_a_sync_decorator_over_an_async_binding_needs_aresolve() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        @override
        def get(self) -> str:
            return self.inner.get().upper()

    async def store() -> Store:
        return Store()

    di = Container().bind(store).decorate(Store, Loud).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Store)
    assert (await di.aresolve(Store)).get() == 'PLAIN'


async def test_a_consumer_of_a_decorated_async_binding_needs_aresolve() -> None:
    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    async def loud(inner: Store) -> Store:
        return Loud(inner)

    di = Container().bind(Store).bind(Service).decorate(Store, loud).freeze()
    assert di.graph().node(Service).needs_async
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Service)


def test_a_decorator_over_an_unbound_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    container = Container().decorate(Store, Loud)
    with pytest.raises(MissingProviderError, match='no binding is registered') as error:
        _ = container.freeze()
    assert 'condition that did not hold' not in str(error.value)


def test_a_decorator_over_a_scope_value_binding_is_rejected() -> None:
    class Principal: ...

    class Loud:
        def __init__(self, inner: Principal) -> None:
            self.inner = inner

    container = Container().scope_value(Principal).decorate(Principal, Loud)
    with pytest.raises(InvalidProviderError, match='scope_value'):
        _ = container.freeze()


def test_a_lifecycle_decorator_over_a_transient_binding_is_rejected() -> None:
    class Store: ...

    def loud(inner: Store) -> Generator[Store]:
        yield inner

    container = Container().bind(Store, scope=Scope.TRANSIENT).decorate(Store, loud)
    with pytest.raises(InvalidScopeError, match='cannot decorate transient'):
        _ = container.freeze()


def test_an_inactive_decorator_leaves_the_binding_bare() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud, when=False).freeze()
    assert di.resolve(Store).get() == 'plain'
    assert di.graph().find(Underlying(Store, 0)) is None


def test_a_decorator_over_an_inactive_binding_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store, when=False).decorate(Store, Loud)
    with pytest.raises(MissingProviderError, match='same condition') as error:
        _ = container.freeze()
    assert 'registered under a condition that did not hold' in str(error.value)
    assert 'no binding is registered' not in str(error.value)


def test_a_decorator_sharing_its_binding_condition_disappears_with_it() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store, when=False).decorate(Store, Loud, when=False).freeze()
    assert di.graph().nodes == ()


def test_decorating_an_underlying_layer_is_rejected() -> None:
    """`Underlying` names an inner layer of a decoration chain the fold produces, constructed
    to inspect a graph rather than to register one, so `decorate` refuses it outright.
    """

    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store).decorate(Underlying(Store, 0), Loud)
    with pytest.raises(InvalidProviderError, match='constructed to inspect a graph'):
        _ = container.freeze()


def test_decorating_an_unbound_key_names_the_key_and_the_remedy() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().decorate(Store, Loud)
    with pytest.raises(MissingProviderError) as error:
        _ = container.freeze()
    assert str(error.value) == (
        'cannot decorate test_decorating_an_unbound_key_names_the_key_and_the_remedy.<locals>.Store '
        '(tag=None): no binding is registered for it. A decorator wraps an existing binding, so bind '
        'the key, drop the decorator, or give the decorator the same condition as the binding it wraps.'
    )


def test_decorating_an_inactive_binding_names_the_condition() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store, when=False).decorate(Store, Loud)
    with pytest.raises(MissingProviderError) as error:
        _ = container.freeze()
    assert str(error.value) == (
        'cannot decorate test_decorating_an_inactive_binding_names_the_condition.<locals>.Store '
        '(tag=None): its binding is registered under a condition that did not hold, so nothing was '
        'bound for it in this configuration. Give the decorator the same condition as the binding it wraps.'
    )


def test_decorating_a_scope_value_names_the_frame() -> None:
    class Principal: ...

    class Loud:
        def __init__(self, inner: Principal) -> None: ...

    container = Container().scope_value(Principal).decorate(Principal, Loud)
    with pytest.raises(InvalidProviderError) as error:
        _ = container.freeze()
    assert str(error.value) == (
        'cannot decorate test_decorating_a_scope_value_names_the_frame.<locals>.Principal (tag=None): '
        'it is declared with scope_value(), and a value supplied by whoever opens the scope is read '
        'from the active frame before the plan is consulted, so a parameter would receive the '
        'undecorated value. Wrap the value where the scope is opened instead.'
    )


def test_decorating_a_transient_with_a_lifecycle_wrapper_names_the_drain() -> None:
    class Store: ...

    def loud(inner: Store) -> Generator[Store]:
        yield inner

    container = Container().bind(Store, scope=Scope.TRANSIENT).decorate(Store, loud)
    with pytest.raises(InvalidScopeError) as error:
        _ = container.freeze()
    assert str(error.value) == (
        'cannot decorate transient '
        'test_decorating_a_transient_with_a_lifecycle_wrapper_names_the_drain.<locals>.Store '
        f'with {loud!r}: a generator or context-manager decorator owns a teardown, and a transient '
        'value is never cached, so nothing would drain it. Bind the key as singleton or scoped.'
    )


def test_the_rewritten_inner_parameter_is_required_and_not_optional() -> None:
    """The layer below always exists, so the fold strips the default and the `| None` off `inner`."""

    class Store: ...

    class Loud(Store):
        def __init__(self, inner: Store | None = None) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    (edge,) = di.graph().node(Store).dependencies
    assert edge.parameter == 'inner'
    assert edge.key == Underlying(Store, 0)
    assert edge.satisfied is True
    assert edge.has_default is False
    assert edge.optional is False
    resolved = di.resolve(Store)
    assert isinstance(resolved, Loud)
    assert isinstance(resolved.inner, Store)
