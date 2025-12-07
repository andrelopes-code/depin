from depin import Container, Inject, Scope


def test_function_provider_with_dependencies():
    c = Container()

    class Config:
        def __init__(self):
            self.value = 100

    def get_service(config: Config):
        return config.value * 2

    c.bind(source=Config, scope=Scope.SINGLETON)
    c.bind(source=get_service, scope=Scope.SINGLETON)

    result = c.get(get_service)
    assert result == 200


def test_function_provider_with_multiple_dependencies():
    c = Container()

    def dep1():
        return 10

    def dep2():
        return 20

    def service(a: int = Inject(dep1), b: int = Inject(dep2)):
        return a + b

    c.bind(source=dep1, scope=Scope.SINGLETON)
    c.bind(source=dep2, scope=Scope.SINGLETON)
    c.bind(source=service, scope=Scope.SINGLETON)

    assert c.get(service) == 30


def test_function_provider_with_default_params():
    c = Container()

    def service(value: int = 99):
        return value * 2

    c.bind(source=service, scope=Scope.SINGLETON)

    assert c.get(service) == 198
