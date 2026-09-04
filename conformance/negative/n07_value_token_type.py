"""`Container.value()` rejects a value incompatible with its `Token`."""

from depin import Container, Token

port = Token[int]('port')


def main() -> None:
    _ = Container().value(port, 'not-a-port')
