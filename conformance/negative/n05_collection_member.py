"""`collect()` given a member that is not a provider key.

`ProviderKey` admits a class, a `Token`, a string, a parameterised generic
alias and an `Underlying`. An integer is none of them, so it cannot stand in a
collection's member sequence.
"""

from typing import Protocol

from depin import Container


class Handler(Protocol):
    def run(self) -> str: ...


class Email:
    def run(self) -> str:
        return 'email'


def main() -> None:
    _ = Container().bind(Email).collect(Handler, [Email, 42])
