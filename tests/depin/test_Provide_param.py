from di_framework import Container, Provide, Scope


def test_provide_explicit_dependency():
    c = Container()

    def get_config():
        return {'env': 'prod'}

    class Service:
        def __init__(self, config: dict[str, str] = Provide(get_config)):
            self.config = config

    c.register(provider_fn=get_config, scope=Scope.SINGLETON)
    c.register(implementation=Service, scope=Scope.SINGLETON)

    s = c.resolve(Service)
    assert s.config['env'] == 'prod'


def test_provide_overrides_type_hint():
    c = Container()

    def get_string():
        return 'from_provider'

    class Service:
        def __init__(self, value: int = Provide(get_string)):  # type: ignore
            self.value = value

    c.register(provider_fn=get_string, scope=Scope.SINGLETON)
    c.register(implementation=Service, scope=Scope.SINGLETON)

    s = c.resolve(Service)
    assert s.value == 'from_provider'


def test_provide_with_nested_dependencies():
    c = Container()

    def get_db():
        return 'DB_CONNECTION'

    def get_repo(db: str = Provide(get_db)):
        return f'REPO:{db}'

    class Service:
        def __init__(self, repo: str = Provide(get_repo)):
            self.repo = repo

    c.register(provider_fn=get_db, scope=Scope.SINGLETON)
    c.register(provider_fn=get_repo, scope=Scope.SINGLETON)
    c.register(implementation=Service, scope=Scope.SINGLETON)

    s = c.resolve(Service)
    assert s.repo == 'REPO:DB_CONNECTION'
