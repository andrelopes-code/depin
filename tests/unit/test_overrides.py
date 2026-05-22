from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope


def test_override_with_value() -> None:
    class A:
        def __init__(self) -> None:
            self.v = 1

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    fake = A()
    fake.v = 99
    with frozen.override(A, with_=fake):
        assert frozen[A].v == 99
    assert frozen[A].v == 1


def test_override_token() -> None:
    db_url = Token[str]('db.url')
    frozen = Container().value(db_url, 'prod').freeze()
    with frozen.override(db_url, with_='test'):
        assert frozen[db_url] == 'test'
    assert frozen[db_url] == 'prod'


def test_override_with_factory_callable() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    with frozen.override(A, with_=lambda: A()):
        a1 = frozen[A]
        a2 = frozen[A]
    assert a1 is not a2
