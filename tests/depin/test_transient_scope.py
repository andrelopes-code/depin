from depin import Container, Scope


def test_transient_class_different_instances():
    c = Container()

    class A: ...

    c.register(source=A, scope=Scope.TRANSIENT)

    a1 = c.resolve(A)
    a2 = c.resolve(A)
    a3 = c.resolve(A)

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

    c.register(source=provider, scope=Scope.TRANSIENT)

    assert c.resolve(provider) == 1
    assert c.resolve(provider) == 2
    assert c.resolve(provider) == 3
    assert call_count == 3
