"""Shared types and builders for the tier 1 workloads."""

from collections.abc import Callable
from typing import Protocol

from depin import Container

HOT_GRAPH = 100
"""The graph size every cached-lookup workload uses.

The baseline measured a cached lookup at 2021, 1970, 2033 and 1992 ns over graphs
of 1, 10, 100 and 300 nodes — flat within 3%. The size therefore does not move the
number, and fixing one across the family is what lets the alias and decoration
workloads be read as differences from `resolve_cached_singleton` without the
reader having to know that.
"""

CHAIN_DEPTH = 20
"""The depth the transient and scoped chains construct through, as the suite has always used."""


class Wired:
    """What a hand-wired program holds: one object, reached by attribute access.

    The baseline measured a cached resolution against exactly this — 2.17 µs
    against 0.06 µs for an attribute read on a held object — so the direct
    implementations of the cached-lookup family read through one.
    """

    def __init__(self, value: object) -> None:
        self.value = value


class Element(Protocol):
    """The element key `resolve_collection` gathers its members under."""


class Aliased(Protocol):
    """The second name `resolve_cached_singleton_through_an_alias` resolves through."""


class Repo:
    """The one dependency the injected wrapper receives."""

    def count(self) -> int:
        return 3


class Sole:
    """The single provider the override pair and the generic-key workload resolve.

    One provider rather than the hundred `resolve_cached_singleton` uses, because
    the three of them are read as differences from each other and a chain would
    add a setup cost none of the differences are about. The cached lookup is flat
    in graph size — the baseline measured it within 3% over 1 to 300 nodes — so
    the two families stay comparable anyway.
    """


class Substitute(Sole):
    """What the active override returns in place of the registered provider."""


class Indirect:
    """One level of indirection over a held object.

    The direct counterpart of an active override: hand-wiring reaches the
    substitute through the holder that stands in for the override frame, so the
    baseline performs one more hop than `Wired` alone.
    """

    def __init__(self, inner: Wired) -> None:
        self.inner = inner


class Boxed[T]:
    """The generic origin `resolve_a_generic_key` resolves a parameterisation of.

    Spelled as a subscript rather than built through `types.GenericAlias`, because
    this key is fixed at authoring time and every checker reads `Boxed[Repo]` as a
    key without help. It holds its parameter rather than only declaring one, so
    the argument is inferred at every construction instead of being asserted at
    one.
    """

    def __init__(self, value: T) -> None:
        self.value = value


class Connection:
    """The resource `resolve_a_sync_resource_with_teardown` opens and drains."""


class Pool:
    """The async singleton, whose provider is a coroutine function."""


class Decorated:
    """What a decorator returns: the wrapped value, held."""

    def __init__(self, inner: object) -> None:
        self.inner = inner


class Middle(Decorated):
    """The inner of the two decorators over the leaf."""


class Outer(Decorated):
    """The outer of the two decorators over the leaf."""


async def _ready(value: object) -> object:
    """The bare coroutine the async baseline drives through the same event loop."""
    return value


def _decoration(wrapper: type[Decorated], node: type[object]) -> Callable[..., object]:
    """A decorator over `node` returning a `wrapper`, annotated the way `graphs._provider` is."""

    def wrap(inner: object) -> object:
        return wrapper(inner)

    wrap.__annotations__ = {'inner': node, 'return': node}
    return wrap


def _boxed() -> Boxed[Repo]:
    return Boxed(Repo())


def _sole() -> Sole:
    return Sole()


def _construct_chain(nodes: tuple[type[object], ...]) -> object:
    """Construct every class in `nodes`, in order, and return the last."""
    made: object = None
    for node in nodes:
        made = node()
    return made


def _construct_recorded(nodes: tuple[type[object], ...], log: list[str]) -> object:
    """`_construct_chain`, naming each class in `log` as it is constructed."""
    made: object = None
    for node in nodes:
        log.append(node.__name__)
        made = node()
    return made


def _build_collection(size: int) -> Container:
    """`size` independently bound members, gathered under `list[Element]`."""
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = type(f'Member{index}', (), {})

        def make(node: type[object] = member) -> object:
            return node()

        make.__annotations__ = {'return': member}
        container = container.bind(make, provides=member)
        members.append(member)
    return container.collect(Element, members)


def _collection_result(members: list[Element]) -> str:
    return f'list[{len(members)}] {type(members[0]).__name__}..{type(members[-1]).__name__}'
