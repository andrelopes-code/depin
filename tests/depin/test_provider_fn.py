from di_framework import Container, Provide, Scope


def test_function_provider_with_dependencies():
    c = Container()

    class Config:
        def __init__(self):
            self.value = 100

    def get_service(config: Config):
        return config.value * 2

    c.register(implementation=Config, scope=Scope.SINGLETON)
    c.register(provider_fn=get_service, scope=Scope.SINGLETON)

    result = c.resolve(get_service)
    assert result == 200


def test_function_provider_with_multiple_dependencies():
    c = Container()

    def dep1():
        return 10

    def dep2():
        return 20

    def service(a: int = Provide(dep1), b: int = Provide(dep2)):
        return a + b

    c.register(provider_fn=dep1, scope=Scope.SINGLETON)
    c.register(provider_fn=dep2, scope=Scope.SINGLETON)
    c.register(provider_fn=service, scope=Scope.SINGLETON)

    assert c.resolve(service) == 30


def test_function_provider_with_default_params():
    c = Container()

    def service(value: int = 99):
        return value * 2

    c.register(provider_fn=service, scope=Scope.SINGLETON)

    assert c.resolve(service) == 198
