from dataclasses import dataclass

from depin import Container, Provide, Scope


def test_resolve_dataclass_dependencies():
    c = Container()

    def provider():
        return 21

    @dataclass
    class C:
        f: int = Provide(provider)

    @dataclass
    class B:
        c: C

    @dataclass
    class A:
        b: B

    c.register(source=A, scope=Scope.TRANSIENT)
    c.register(source=B, scope=Scope.TRANSIENT)
    c.register(source=C, scope=Scope.TRANSIENT)
    c.register(source=provider, scope=Scope.TRANSIENT)

    a = c.resolve(A)

    assert isinstance(a, A)
    assert a.b.c.f == 21
