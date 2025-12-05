import pytest

from depin import Container, Scope


@pytest.mark.skip('did not raise')
def test_register_function_with_class_raises():
    c = Container()

    class A: ...

    def provider():
        return A()

    with pytest.raises(ValueError, match='apenas um provider'):
        c.register(abstract=A, source=provider, scope=Scope.SINGLETON)


def test_resolve_unregistered_raises():
    c = Container()

    class A: ...

    with pytest.raises(ValueError, match='not registered'):
        c.resolve(A)


def test_resolve_unregistered_function_raises():
    c = Container()

    def provider():
        return 1

    with pytest.raises(ValueError, match='not registered'):
        c.resolve(provider)
