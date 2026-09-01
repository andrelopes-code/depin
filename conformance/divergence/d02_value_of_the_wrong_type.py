"""`Container.value()` given a value of a type the token does not carry.

Four of the five checkers accept this; Pyrefly rejects it. The disagreement is
about `Token[T]`, whose parameter is phantom — it appears in no member — so the
typing specification's variance-inference algorithm tests covariance first and a
phantom parameter passes that test. Four checkers therefore infer ``T``
covariant, solve it at ``object``, and accept a `str` for a ``Token[int]``.
Pyrefly 1.2.0 infers invariance and catches the call.

The remedy that repairs it for the other four is R5, which changes no call site;
the roadmap took R4 instead, at ``2816b09``, and R4 leaves ``T`` phantom. So
this is the baseline's state rather than a regression, and it is routed to Step
8 with `d01_override_replacement.py`.

Four of the eight remedies measured for the variance experiment would have made
Pyrefly accept this too. Recording its rejection as an expected verdict is what
makes that loss visible if it ever happens.
"""

from depin import Container, Token

port = Token[int]('port')


def main() -> None:
    _ = Container().value(port, 'not-a-port')
