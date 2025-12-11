import pytest
from fastapi import Request

from depin import Container, Inject, RequestScopeService, Scope


def test_request_scope_same_instance_within_request():
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.bind(source=A, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        a1 = c.get(A)
        a2 = c.get(A)

    assert a1 is a2
    assert A.call_count == 1


def test_request_scope_different_instances_across_requests():
    c = Container()

    class A: ...

    c.bind(source=A, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        a1 = c.get(A)

    with RequestScopeService.request_scope():
        a2 = c.get(A)

    assert a1 is not a2


def test_request_scope_function_called_once_per_request():
    c = Container()
    call_count = 0

    def provider():
        nonlocal call_count
        call_count += 1
        return call_count

    c.bind(source=provider, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        r1 = c.get(provider)
        r2 = c.get(provider)

    with RequestScopeService.request_scope():
        r3 = c.get(provider)

    assert r1 == r2 == 1
    assert r3 == 2
    assert call_count == 2


def test_bind_fastapi_Request_to_the_request_scope():
    c = Container()

    c.bind(
        abstract=Request,
        source=lambda: RequestScopeService.get_current_request(),
        scope=Scope.REQUEST,
    )

    fake_request = Request(scope={'type': 'http'})

    with RequestScopeService.request_scope():
        RequestScopeService.set_current_request(fake_request)

        request = c.get(Request)
        assert request is fake_request


def test_raises_when_fastapi_Request_is_requested_but_not_in_the_request_scope():
    c = Container()

    c.bind(
        abstract=Request,
        source=lambda: RequestScopeService.get_current_request(),
        scope=Scope.REQUEST,
    )

    with pytest.raises(RuntimeError, match='No Request instance found in the current request scope'):
        c.get(Request)


@pytest.mark.asyncio
async def test_request_scope_class_async_provider():
    c = Container()

    @c.register(Scope.REQUEST)
    async def async_dep():
        return 'async_dep'

    @c.register(Scope.REQUEST)
    class A:
        def __init__(self, async_dep: str = Inject(async_dep)) -> None:
            self.async_dep = async_dep

    with RequestScopeService.request_scope():
        a1 = await c.get_async(A)

    assert a1.async_dep == 'async_dep'


@pytest.mark.asyncio
async def test_async_generator_in_request_scope():
    c = Container()

    async def async_gen():
        yield 23

    c.bind(source=async_gen, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        n = await c.get_async(async_gen)

    assert n == 23


def test_generator_in_request_scope():
    c = Container()

    def gen():
        yield 23

    c.bind(source=gen, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        n = c.get(gen)

    assert n == 23


@pytest.mark.asyncio
async def test_async_generator_cleanup_after_request_end():
    c = Container()
    cleaned = []

    @c.register(Scope.REQUEST)
    async def async_gen1():
        yield 11

        cleaned.append(async_gen1)

    @c.register(Scope.REQUEST)
    async def async_gen2():
        yield 22

        cleaned.append(async_gen2)

    async with RequestScopeService.request_scope_async():
        ag1 = await c.get_async(async_gen1)
        ag2 = await c.get_async(async_gen2)

        assert ag1 == 11
        assert ag2 == 22
        assert cleaned == []

    assert cleaned == [async_gen2, async_gen1]


def test_generator_cleanup_after_request_end():
    c = Container()
    cleaned = []

    @c.register(Scope.REQUEST)
    def gen1():
        yield 11

        cleaned.append(gen1)

    @c.register(Scope.REQUEST)
    def gen2():
        yield 22

        cleaned.append(gen2)

    with RequestScopeService.request_scope():
        ag1 = c.get(gen1)
        ag2 = c.get(gen2)

        assert ag1 == 11
        assert ag2 == 22
        assert cleaned == []

    assert cleaned == [gen2, gen1]


def test_cleanup_in_reverse_order():
    c = Container()
    cleaned = []

    @c.register(Scope.REQUEST)
    def gen1():
        yield

        cleaned.append(gen1)

    @c.register(Scope.REQUEST)
    def gen2():
        yield

        cleaned.append(gen2)

    @c.register(Scope.REQUEST)
    def gen3():
        yield

        cleaned.append(gen3)

    with RequestScopeService.request_scope():
        _ = c.get(gen1)
        _ = c.get(gen2)
        _ = c.get(gen3)

        assert cleaned == []

    assert cleaned == [gen3, gen2, gen1]
