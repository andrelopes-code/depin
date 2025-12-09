import pytest

from depin import Container, Inject, Scope
from depin._internal.exceptions import MissingProviderError


def test_dependency_with_no_provider_and_no_default_raises():
    c = Container()

    class B: ...

    class A:
        def __init__(self, b: B): ...

    c.bind(source=A, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError, match='Cannot resolve parameter'):
        c.get(A)


def test_dependency_with_default_value_uses_default():
    c = Container()

    class A:
        def __init__(self, value: int = 42):
            self.value = value

    c.bind(source=A, scope=Scope.SINGLETON)
    a = c.get(A)

    assert a.value == 42


def test_deep_dependency_chain():
    c = Container()

    class D:
        def __init__(self):
            self.name = 'D'

    class C:
        def __init__(self, d: D):
            self.d = d

    class B:
        def __init__(self, c: C):
            self.c = c

    class A:
        def __init__(self, b: B):
            self.b = b

    c.bind(source=D, scope=Scope.SINGLETON)
    c.bind(source=C, scope=Scope.SINGLETON)
    c.bind(source=B, scope=Scope.SINGLETON)
    c.bind(source=A, scope=Scope.SINGLETON)

    a = c.get(A)

    assert a.b.c.d.name == 'D'


def test_circular_dependency_singleton():
    """Circular dependencies em singleton devem funcionar devido ao lazy loading"""
    c = Container()

    class B:
        def __init__(self):
            self.name = 'B'

    class A:
        def __init__(self, b: B):
            self.b = b

    c.bind(source=B, scope=Scope.SINGLETON)
    c.bind(source=A, scope=Scope.SINGLETON)

    a = c.get(A)
    assert isinstance(a.b, B)


def test_multiple_dependencies_same_class():
    c = Container()

    class Service:
        def __init__(self):
            self.id = id(self)

    class Consumer:
        def __init__(self, s1: Service, s2: Service):
            self.s1 = s1
            self.s2 = s2

    c.bind(source=Service, scope=Scope.SINGLETON)
    c.bind(source=Consumer, scope=Scope.SINGLETON)

    consumer = c.get(Consumer)

    # Com SINGLETON, s1 e s2 devem ser a mesma instância
    assert consumer.s1 is consumer.s2


def test_multiple_dependencies_different_scopes():
    c = Container()

    class Singleton:
        call_count = 0

        def __init__(self):
            Singleton.call_count += 1

    class Transient:
        call_count = 0

        def __init__(self):
            Transient.call_count += 1

    class Consumer:
        def __init__(self, s: Singleton, t: Transient):
            self.s = s
            self.t = t

    c.bind(source=Singleton, scope=Scope.SINGLETON)
    c.bind(source=Transient, scope=Scope.TRANSIENT)
    c.bind(source=Consumer, scope=Scope.TRANSIENT)

    c1 = c.get(Consumer)
    c2 = c.get(Consumer)

    assert Singleton.call_count == 1
    assert Transient.call_count == 2
    assert c1.s is c2.s
    assert c1.t is not c2.t


def test_nested_classes():
    c = Container()

    class D: ...

    class C:
        def __init__(self, default_param='default') -> None:
            self.default_param = default_param

    class B:
        def __init__(self, c: C, d: D) -> None:
            self.c = c
            self.d = d

    class A:
        def __init__(self, b: B) -> None:
            self.b = b

    c.bind(source=A, scope=Scope.TRANSIENT)
    c.bind(source=B, scope=Scope.SINGLETON)
    c.bind(source=C, scope=Scope.SINGLETON)
    c.bind(source=D, scope=Scope.SINGLETON)

    a = c.get(A)

    assert isinstance(a, A)
    assert isinstance(a.b, B)
    assert isinstance(a.b.c, C)
    assert isinstance(a.b.d, D)
    assert a.b.c.default_param == 'default'


def test_nested_class_not_registered():
    c = Container()

    class C: ...

    class B:
        # C is not registered in container
        def __init__(self, c: C) -> None:
            self.c = c

    class A:
        def __init__(self, b: B) -> None:
            self.b = b

    c.bind(source=A, scope=Scope.TRANSIENT)
    c.bind(source=B, scope=Scope.SINGLETON)

    with pytest.raises(MissingProviderError, match='Cannot resolve parameter'):
        c.get(A)


def test_nested_functions():
    c = Container()

    def D1():
        return 1

    def D2():
        return 2

    def D3(d1: int = Inject(D1), d2: int = Inject(D2)):
        return d1 + d2

    c.bind(source=D1, scope=Scope.TRANSIENT)
    c.bind(source=D2, scope=Scope.TRANSIENT)
    c.bind(source=D3, scope=Scope.TRANSIENT)

    d = c.get(D3)

    assert d == 3


def test_mixed_classes_and_functions():
    c = Container()

    def f2():
        return 2

    class B: ...

    class A:
        def __init__(self, b: B, f2: int = Inject(f2), default='default') -> None:
            self.default = default
            self.f2 = f2
            self.b = b

    def f1(a: A):
        return a

    c.bind(source=f2, scope=Scope.SINGLETON)
    c.bind(source=f1, scope=Scope.TRANSIENT)
    c.bind(source=B, scope=Scope.SINGLETON)
    c.bind(source=A, scope=Scope.SINGLETON)

    r1 = c.get(f1)

    assert isinstance(r1, A)
    assert isinstance(r1.b, B)
    assert r1.f2 == 2
    assert r1.default == 'default'
