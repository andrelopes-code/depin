"""`@inject` and `injected()`, from the call site.

The wrapper's own type is not asserted anywhere in this file, and that is
deliberate. An injected parameter survives into the wrapper's signature carrying
its marker default, so the wrapper is `Callable[[str, int, Config], str]` rather
than `Callable[[str, int], str]` under every checker; asserting the callable
would state a promise the library does not make. What the library promises is
the call site, so that is what is asserted: the return type, the parameters the
caller must still pass, and the parameter it may pass explicitly to override the
container.

The async wrapper is an assignability promise. Both `inject` overloads match an
``async def`` — four checkers pick the first and ty the second, which gives
`CoroutineType[Any, Any, str]` — and every operation `Awaitable[str]` promises
survives that choice. It takes a typed witness.
"""

from collections.abc import Awaitable
from typing import Protocol, assert_type

from depin import Container, FrozenContainer, Token, injected


class Config:
    def __init__(self, value: int = 1) -> None:
        self.value = value


class Handler(Protocol):
    def run(self) -> str: ...


class Email:
    def run(self) -> str:
        return 'email'


port = Token[int]('port')


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Email).collect(Handler, [Email]).value(port, 8080).freeze()


def a_sync_wrapper_keeps_its_return_type() -> None:
    di = build()

    @di.inject
    def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    assert_type(handler('n'), str)


def a_sync_wrapper_keeps_the_parameters_the_caller_still_passes() -> None:
    di = build()

    @di.inject
    def handler(label: str, retries: int, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}:{retries}'

    assert_type(handler('n', 3), str)
    assert_type(handler(label='n', retries=3), str)


def an_injected_parameter_may_still_be_passed_explicitly() -> None:
    di = build()

    @di.inject
    def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    assert_type(handler('n', Config(2)), str)
    assert_type(handler('n', config=Config(2)), str)


def a_wrapper_returning_a_container_type_keeps_it() -> None:
    di = build()

    @di.inject
    def pick(config: Config = injected(Config)) -> Config:
        return config

    assert_type(pick(), Config)


def an_async_wrapper_stays_awaitable_at_its_return_type() -> None:
    di = build()

    @di.inject
    async def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    # Nested and never called: the promise is checked statically, and calling
    # the wrapper here would leave an un-awaited coroutine behind.
    def call_site() -> None:
        _pending: Awaitable[str] = handler('n')
        _explicit: Awaitable[str] = handler('n', Config(2))

    _ = call_site


async def an_awaited_wrapper_yields_its_return_type() -> None:
    di = build()

    @di.inject
    async def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    assert_type(await handler('n'), str)


def injected_takes_the_type_of_its_key() -> None:
    assert_type(injected(Config), Config)
    assert_type(injected(port), int)


def injected_takes_the_type_of_a_parameterised_key() -> None:
    assert_type(injected(list[Handler]), list[Handler])


def injected_carries_a_tag_without_changing_its_type() -> None:
    assert_type(injected(Config, tag='primary'), Config)
