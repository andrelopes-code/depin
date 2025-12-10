import pytest

from depin import Container, Inject, Scope


def test_singleton_class_same_instance():
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.bind(source=A, scope=Scope.SINGLETON)

    a1 = c.get(A)
    a2 = c.get(A)
    a3 = c.get(A)

    assert a1 is a2 is a3
    assert A.call_count == 1


def test_singleton_function_called_once():
    c = Container()
    call_count = 0

    def provider():
        nonlocal call_count
        call_count += 1
        return {'value': call_count}

    c.bind(source=provider, scope=Scope.SINGLETON)

    r1 = c.get(provider)
    r2 = c.get(provider)
    r3 = c.get(provider)

    assert r1 is r2 is r3
    assert call_count == 1
    assert r1['value'] == 1


def test_override_singleton_dependency():
    c = Container()

    class Abs: ...

    def provider1():
        return 42

    def provider2():
        return 19

    p1_1 = c.bind(abstract=Abs, source=provider1, scope=Scope.SINGLETON)

    p1_1 = c.get(Abs)
    p1_2 = c.get(Abs)

    assert p1_1 is p1_2
    assert p1_1 == 42

    c.bind(abstract=Abs, source=provider2, scope=Scope.SINGLETON)

    p2_1 = c.get(Abs)
    p2_2 = c.get(Abs)

    assert p2_1 is p2_2
    assert p2_1 == 19


def test_resolve_singleton_in_class_variable():
    c = Container()

    @c.register(Scope.SINGLETON)
    def get_num():
        return 89

    class A:
        num = c.get(get_num)

    assert A.num == 89


@pytest.mark.asyncio
async def test_singleton_class_that_needs_async():
    c = Container()

    async def async_dep_func():
        return 'async'

    class A:
        def __init__(self, async_dep: str = Inject(async_dep_func)):
            self.async_dep = async_dep

    c.bind(source=A, scope=Scope.SINGLETON)
    c.bind(source=async_dep_func, scope=Scope.SINGLETON)

    a1 = await c.get_async(A)
    a2 = await c.get_async(A)
    a3 = await c.get_async(A)

    assert a1 is a2 is a3
