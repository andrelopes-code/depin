"""`FrozenContainer.override()` given a replacement of an unrelated type.

This is a false negative in the public API, not a fixture the suite wants
rejected today: all five checkers accept it. `override` is declared
``(key: type[T] | Token[T], replacement: T)``, and `type[T]` is covariant by
construction in the typing specification, so ``T`` is solved at a supertype of
both `Config` and `Other` — ``object`` — and the call is well typed.

No `Token` remedy reaches it: the parameterisation that would is `override`'s
own, and the measured repair changes the call shape to
``override[T](key).using(replacement)``. It is routed to Step 8, which is the
last window before the API freezes.

A fixture every checker accepts gates nothing, so this cannot live in
`negative/`. `expected/divergence.toml` records the verdict of each checker
today and the harness fails when one changes **in either direction**: a checker
that starts rejecting this is news the project wants, and a checker that stops
rejecting the fixture beside it is a regression.
"""

from depin import Container


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Other:
    def __init__(self) -> None:
        self.name = 'other'


def main() -> None:
    di = Container().bind(Config).freeze()
    with di.override(Config, Other()) as overridden:
        _ = overridden.resolve(Config)
