from dataclasses import dataclass

from di_framework import Container, Provide, Scope


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

    c.register(implementation=A, scope=Scope.TRANSIENT)
    c.register(implementation=B, scope=Scope.TRANSIENT)
    c.register(implementation=C, scope=Scope.TRANSIENT)
    c.register(provider_fn=provider, scope=Scope.TRANSIENT)

    a = c.resolve(A)

    assert isinstance(a, A)
    assert a.b.c.f == 21
