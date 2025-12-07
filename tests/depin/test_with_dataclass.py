from dataclasses import dataclass

from depin import Container, Inject, Scope
from depin.internal.types import ProviderDependency


def test_resolve_dataclass_dependencies():
    c = Container()

    def provider():
        return 21

    @dataclass
    class C:
        f: int = Inject(provider)

    @dataclass
    class B:
        c: C

    @dataclass
    class A:
        b: B

    c.bind(source=A, scope=Scope.TRANSIENT)
    c.bind(source=B, scope=Scope.TRANSIENT)
    c.bind(source=C, scope=Scope.TRANSIENT)
    c.bind(source=provider, scope=Scope.TRANSIENT)

    a = c.get(A)

    assert isinstance(a, A)
    assert a.b.c.f == 21


def test_dataclass_Inject_function_without_type_hint():
    c = Container()

    @c.register(Scope.REQUEST)
    class A:
        pass

    @c.register(Scope.REQUEST)
    @dataclass
    class B:
        a = Inject(A)

    b = c.get(B)

    assert isinstance(b, B)
    assert isinstance(b.a, ProviderDependency)


def test_dataclass_Inject_function_with_wrong_type_hint():
    c = Container()

    @c.register(Scope.REQUEST)
    class A:
        pass

    @c.register(Scope.REQUEST)
    class K:
        pass

    @c.register(Scope.REQUEST)
    @dataclass
    class B:
        a: K = Inject(A)  # type: ignore

    b = c.get(B)

    assert isinstance(b, B)
    assert isinstance(b.a, A)
