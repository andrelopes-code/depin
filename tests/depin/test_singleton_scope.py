from di_framework import Container, Scope


def test_singleton_class_same_instance():
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.register(source=A, scope=Scope.SINGLETON)

    a1 = c.resolve(A)
    a2 = c.resolve(A)
    a3 = c.resolve(A)

    assert a1 is a2 is a3
    assert A.call_count == 1


def test_singleton_function_called_once():
    c = Container()
    call_count = 0

    def provider():
        nonlocal call_count
        call_count += 1
        return {'value': call_count}

    c.register(source=provider, scope=Scope.SINGLETON)

    r1 = c.resolve(provider)
    r2 = c.resolve(provider)
    r3 = c.resolve(provider)

    assert r1 is r2 is r3
    assert call_count == 1
    assert r1['value'] == 1
