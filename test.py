from dataclasses import dataclass

from depin import Container, Inject, Scope

c = Container()


@c.register(Scope.REQUEST)
class A:
    pass


@c.register(Scope.REQUEST)
@dataclass
class B:
    # parametros sem type hint não funcionam
    # em dataclasses, o parametro não aparece
    # na signature da classe.
    a = Inject(A)


@c.register(Scope.REQUEST)
class G:
    # parametros sem type hint funcionam no __init__
    def __init__(self, a=Inject(A)) -> None:
        self.a = a


@c.register(Scope.REQUEST)
@dataclass
class K:
    inst: G = Inject(A)  # type: ignore


b = c.get(B)

# assert isinstance(b, B)
# assert isinstance(b.a, A)

g = c.get(G)

assert isinstance(g, G)
assert isinstance(g.a, A)

k = c.get(K)

assert isinstance(k, K)
assert isinstance(k.inst, A)
