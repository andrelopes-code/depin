from depin import Container, Inject, Scope


def test_inject_simple():
    c = Container()

    class Service:
        def __init__(self):
            self.value = 42

    c.bind(source=Service, scope=Scope.SINGLETON)

    @c.inject
    def handler(service: Service = Inject(Service)):
        return service.value

    assert handler() == 42


def test_inject_with_explicit_params():
    c = Container()

    class Service:
        def __init__(self):
            self.value = 42

    c.bind(source=Service, scope=Scope.SINGLETON)

    @c.inject
    def handler(multiplier: int, service: Service = Inject(Service)):
        return service.value * multiplier

    assert handler(multiplier=2) == 84


def test_inject_partial_override():
    c = Container()

    class Service:
        def __init__(self, value=10):
            self.value = value

    c.bind(source=Service, scope=Scope.SINGLETON)

    @c.inject
    def handler(service: Service = Inject(Service)):
        return service.value

    other = Service(20)
    assert handler(service=other) == 20


def test_inject_no_injectable_params():
    c = Container()

    @c.inject
    def handler(x: int, y: int):
        return x + y

    assert handler(5, 10) == 15


def test_inject_preserves_metadata():
    c = Container()

    @c.inject
    def my_function(x: int):
        """This is a docstring"""
        return x * 2

    assert my_function.__name__ == 'my_function'
    assert my_function.__doc__ == 'This is a docstring'


def xxx():
    c = Container()

    def get_num():
        return 75

    class A:
        @c.inject
        def __init__(self, num: int = Inject(get_num)):
            self.num = num

    a = A()

    assert a.num == 75
