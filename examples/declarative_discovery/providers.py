"""Local provider declarations closed into an immutable catalogue."""

from dataclasses import dataclass

from depin import Catalog, Scope, provider


@dataclass(frozen=True, slots=True)
class Settings:
    greeting: str


class Greeter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def render(self, name: str) -> str:
        return f'{self.settings.greeting}, {name}!'


def load_settings() -> Settings:
    return Settings(greeting='Hello')


providers = Catalog(
    __name__,
    provider(load_settings).configure(scope=Scope.TRANSIENT),
    provider(Greeter),
)
