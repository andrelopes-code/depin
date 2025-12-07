from depin import Container, Inject, Scope


def test_provide_explicit_dependency():
    c = Container()

    def get_config():
        return {'env': 'prod'}

    class Service:
        def __init__(self, config: dict[str, str] = Inject(get_config)):
            self.config = config

    c.bind(source=get_config, scope=Scope.SINGLETON)
    c.bind(source=Service, scope=Scope.SINGLETON)

    s = c.get(Service)
    assert s.config['env'] == 'prod'


def test_provide_overrides_type_hint():
    c = Container()

    def get_string():
        return 'from_provider'

    class Service:
        def __init__(self, value: int = Inject(get_string)):  # type: ignore[assignment]
            self.value = value

    c.bind(source=get_string, scope=Scope.SINGLETON)
    c.bind(source=Service, scope=Scope.SINGLETON)

    s = c.get(Service)
    assert s.value == 'from_provider'  # type: ignore[comparison-overlap]


def test_provide_with_nested_dependencies():
    c = Container()

    def get_db():
        return 'DB_CONNECTION'

    def get_repo(db: str = Inject(get_db)):
        return f'REPO:{db}'

    class Service:
        def __init__(self, repo: str = Inject(get_repo)):
            self.repo = repo

    c.bind(source=get_db, scope=Scope.SINGLETON)
    c.bind(source=get_repo, scope=Scope.SINGLETON)
    c.bind(source=Service, scope=Scope.SINGLETON)

    s = c.get(Service)
    assert s.repo == 'REPO:DB_CONNECTION'
