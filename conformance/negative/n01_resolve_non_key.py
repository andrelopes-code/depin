"""`resolve()` called with a value that is not a key.

One misuse per file, no suppressions. The expected line and rule identifier for
each checker are data, in `conformance/expected/negative.toml`; nothing here
tells a checker what to say, and nothing here silences one.
"""

from depin import Container


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


def main() -> None:
    di = Container().bind(Config).freeze()
    _value = di.resolve(42)
