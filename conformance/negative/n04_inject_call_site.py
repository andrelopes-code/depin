"""An `@inject`-wrapped function called with an argument of the wrong type.

`inject` preserves the wrapped signature, so the parameters the caller still
passes keep their declared types. A wrapper that had degraded to
``Callable[..., Any]`` would accept this call.
"""

from depin import Container, injected


class Config:
    value: int = 1


def main() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    _ = handler(42)
