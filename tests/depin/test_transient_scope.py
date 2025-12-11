import pytest

from depin import Container, Inject, Scope


def test_transient_class_different_instances():
    c = Container()

    class A: ...

    c.bind(source=A, scope=Scope.TRANSIENT)

    a1 = c.get(A)
    a2 = c.get(A)
    a3 = c.get(A)

    assert a1 is not a2
    assert a2 is not a3
    assert a1 is not a3


def test_transient_function_called_every_time():
    c = Container()
    call_count = 0

    def provider():
        nonlocal call_count
        call_count += 1
        return call_count

    c.bind(source=provider, scope=Scope.TRANSIENT)

    assert c.get(provider) == 1
    assert c.get(provider) == 2
    assert c.get(provider) == 3
    assert call_count == 3


@pytest.mark.asyncio
async def test_transient_class_async_provider():
    c = Container()

    @c.register(Scope.TRANSIENT)
    async def async_dep():
        return 'async_dep'

    @c.register(Scope.TRANSIENT)
    class A:
        def __init__(self, async_dep: str = Inject(async_dep)) -> None:
            self.async_dep = async_dep

    a1 = await c.get_async(A)
    a2 = await c.get_async(A)
    a3 = await c.get_async(A)

    assert a1 is not a2
    assert a2 is not a3
    assert a1 is not a3

    assert a1.async_dep == 'async_dep'
    assert a2.async_dep == 'async_dep'
    assert a3.async_dep == 'async_dep'
