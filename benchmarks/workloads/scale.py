"""Tier 4: how cost grows with size, and the one cliff a curve is pinned against.

A fixed-size workload cannot see a complexity change. The failing freeze was cubic
and the missing-key walk exponential while every timing case in the suite stayed
green, because none of them grew. These workloads grow: each is one point on a
curve, named `<curve>[<size>]`, and the gate compares the ratio between two points
rather than either point on its own.

Nothing here declares `LATENCY`. A curve measured as if it were one operation says
only that the largest size is slow, which is not a finding.

The two curves over the error paths that motivated the tier are no longer here.
Repairing the walks left both paths dominated by a size-independent constant, so
neither curve tracked the quantity it named any more; `benchmarks.harness.unmeasured`
carries the measurement that retired each one and names what covers those paths now.

The module also carries the measured depth cliff. `FrozenContainer.resolve()`
recurses about three stack frames per dependency, so a cold resolve dies at a
chain of `DEPTH_CLIFF` providers on CPython's default limit — while `freeze()`
accepts a thousand and `warmup()` succeeds on the same graph, because warmup
constructs in topological order and every resolve then finds its dependency
cached. That is a public-surface question rather than a performance one, and it is
routed to Step 8. Pinning it here is what stops it moving unnoticed in the
meantime.
"""

import asyncio
import contextlib
import inspect
import json
import os
import subprocess
import sys
import types
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator, Sequence
from functools import partial
from pathlib import Path
from typing import Protocol

from benchmarks.contracts import Claim, Implementation, Metric, Observation, Prepared, Tier, Workload
from benchmarks.harness import HarnessError, is_object, require_integer, require_object
from depin import Container, Scope

FREEZE_SIZES = (100, 200, 400)
DEPTH_SIZES = (10, 40, 160)
FAN_OUT_SIZES = (10, 20, 40)
COLLECTION_SIZES = (10, 100, 200)
TEARDOWN_SIZES = (10, 20, 40)
ASYNC_TEARDOWN_SIZES = (10, 20, 40)
OVERRIDE_NESTING_SIZES = (8, 32, 128)

OVERRIDE_GRAPH = 1
"""The graph the override curve resolves through.

One provider, because the curve is about the override stack and a cached lookup
is flat in graph size — the tier 1 baseline measured it within 3% over 1 to 300
nodes. Anything larger would add setup cost to every size without moving the
number.
"""

DEPTH_CLIFF = 332
FRAMES_PER_PROVIDER = 3

CLIFF_PROBE = """
import json
import sys

from benchmarks.graphs import build_chain
from depin import Scope

deepest = {}
for scope in (Scope.SINGLETON, Scope.TRANSIENT):
    low, high, best = 1, 900, 0
    while low <= high:
        middle = (low + high) // 2
        container, leaf = build_chain(middle, scope=scope)
        frozen = container.freeze()
        try:
            frozen.resolve(leaf)
        except RecursionError:
            high = middle - 1
        else:
            best = middle
            low = middle + 1
    deepest[scope.value] = best
json.dump({'limit': sys.getrecursionlimit(), 'deepest': deepest}, sys.stdout)
"""


class Element(Protocol):
    """The element key every collection curve gathers its members under."""


COLLECTION_KEY = list[Element]


class Trace:
    """Construction and teardown order, recorded only where an observation needs it.

    The same builders serve `prepare` and `observe`. A timed callable runs
    unbounded times, so recording during preparation would grow a list for the
    length of the measurement and change what is being measured.
    """

    __slots__ = ('events', 'recording')

    def __init__(self, *, recording: bool) -> None:
        self.recording = recording
        self.events: list[str] = []

    def record(self, event: str) -> None:
        if self.recording:
            self.events.append(event)


def _node(index: int) -> type[object]:
    return type(f'Node{index}', (), {})


def _source(node: type[object], trace: Trace) -> Callable[..., object]:
    def make() -> object:
        trace.record(node.__name__)
        return node()

    make.__annotations__ = {'return': node}
    return make


def _link(node: type[object], dependency: type[object], trace: Trace) -> Callable[..., object]:
    def make(upstream: object) -> object:
        del upstream
        trace.record(node.__name__)
        return node()

    make.__annotations__ = {'upstream': dependency, 'return': node}
    return make


def _joiner(node: type[object], dependencies: Sequence[type[object]], trace: Trace) -> Callable[..., object]:
    """A provider with one real parameter per dependency.

    `depin` reads parameters from `inspect.signature`, which honours
    `__signature__`. Assigning annotations onto a `**kwargs` function alone would
    declare no parameters at all, and the graph would come out with no edges.
    """

    def make(**parts: object) -> object:
        del parts
        trace.record(node.__name__)
        return node()

    names = [f'part{index}' for index in range(len(dependencies))]
    # `__signature__` is not declared on `FunctionType`, and `inspect.signature`
    # reads it straight out of the function's `__dict__`.
    vars(make)['__signature__'] = inspect.Signature(
        [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=dependency)
            for name, dependency in zip(names, dependencies, strict=True)
        ],
        return_annotation=node,
    )
    make.__annotations__ = dict(zip(names, dependencies, strict=True)) | {'return': node}
    return make


def _resource(node: type[object], trace: Trace) -> Callable[..., object]:
    def make() -> Iterator[object]:
        trace.record(node.__name__)
        yield node()
        trace.record(f'close {node.__name__}')

    make.__annotations__ = {'return': types.GenericAlias(Iterator, (node,))}
    return make


def _chain(size: int, scope: Scope, trace: Trace) -> tuple[Container, type[object]]:
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = _node(index)
        provider = _source(leaf, trace) if previous is None else _link(leaf, previous, trace)
        container = container.bind(provider, provides=leaf, scope=scope)
        previous = leaf
    return container, leaf


def _fan_out(size: int, trace: Trace) -> tuple[Container, type[object]]:
    container = Container()
    leaves: list[type[object]] = []
    for index in range(size):
        leaf = _node(index)
        container = container.bind(_source(leaf, trace), provides=leaf, scope=Scope.TRANSIENT)
        leaves.append(leaf)
    root = type('Root', (), {})
    return container.bind(_joiner(root, leaves, trace), provides=root, scope=Scope.TRANSIENT), root


def _collection(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = _node(index)
        container = container.bind(_source(member, trace), provides=member, scope=Scope.TRANSIENT)
        members.append(member)
    return container.collect(Element, members)


def _resources(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = _node(index)
        container = container.bind(_resource(member, trace), provides=member, scope=Scope.SCOPED)
        members.append(member)
    return container.collect(Element, members)


def _claim(
    *,
    question: str,
    work: str,
    included: str,
    excluded: str,
    semantics: str,
    shape: str,
    valid: tuple[str, ...],
    invalid: tuple[str, ...],
) -> Claim:
    return Claim(
        question=question,
        work=work,
        included=included,
        excluded=excluded,
        semantics=semantics,
        shape=shape,
        concurrency='single-threaded, no event loop, no scope shared between operations',
        metric=Metric.SCALING,
        unit='seconds per operation',
        valid=valid,
        invalid=invalid,
    )


def _freeze_prepare(size: int) -> Prepared:
    container, _ = _chain(size, Scope.SINGLETON, Trace(recording=False))
    return Prepared(call=container.freeze)


def _freeze_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, _ = _chain(size, Scope.SINGLETON, trace)
    frozen = container.freeze()
    return Observation(result=str(len(frozen.graph().nodes)), constructed=tuple(trace.events), closed=())


def _resolve_prepare(size: int) -> Prepared:
    container, leaf = _chain(size, Scope.TRANSIENT, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, leaf))


def _resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, leaf = _chain(size, Scope.TRANSIENT, trace)
    value = container.freeze().resolve(leaf)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_chain(size: int, trace: Trace) -> Callable[[], object]:
    nodes = tuple(_node(index) for index in range(size))

    def run() -> object:
        built: object = None
        for node in nodes:
            trace.record(node.__name__)
            built = node()
        return built

    return run


def _direct_resolve_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_chain(size, Trace(recording=False)))


def _direct_resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_chain(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _fan_out_prepare(size: int) -> Prepared:
    container, root = _fan_out(size, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, root))


def _fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, root = _fan_out(size, trace)
    value = container.freeze().resolve(root)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_fan_out(size: int, trace: Trace) -> Callable[[], object]:
    leaves = tuple(_node(index) for index in range(size))
    root = type('Root', (), {})

    def run() -> object:
        for leaf in leaves:
            trace.record(leaf.__name__)
        trace.record(root.__name__)
        return root()

    return run


def _direct_fan_out_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_fan_out(size, Trace(recording=False)))


def _direct_fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_fan_out(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _members(values: Sequence[object]) -> str:
    """The constructed members, by type name and in order: what a collection observably produced."""
    return ','.join(type(value).__name__ for value in values)


def _collection_prepare(size: int) -> Prepared:
    frozen = _collection(size, Trace(recording=False)).freeze()
    return Prepared(call=partial(frozen.resolve, COLLECTION_KEY))


def _collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = _collection(size, trace).freeze().resolve(COLLECTION_KEY)
    return Observation(result=_members(values), constructed=tuple(trace.events), closed=())


def _direct_collection(size: int, trace: Trace) -> Callable[[], list[object]]:
    members = tuple(_node(index) for index in range(size))

    def run() -> list[object]:
        built: list[object] = []
        for member in members:
            trace.record(member.__name__)
            built.append(member())
        return built

    return run


def _direct_collection_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_collection(size, Trace(recording=False)))


def _direct_collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = _direct_collection(size, trace)()
    return Observation(result=_members(values), constructed=tuple(trace.events), closed=())


def _teardown_call(size: int, trace: Trace) -> Callable[[], str]:
    frozen = _resources(size, trace).freeze()

    def run() -> str:
        with frozen.scope():
            return _members(frozen.resolve(COLLECTION_KEY))

    return run


def _teardown_prepare(size: int) -> Prepared:
    return Prepared(call=_teardown_call(size, Trace(recording=False)))


def _split_events(trace: Trace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    opened = tuple(event for event in trace.events if not event.startswith('close '))
    closed = tuple(event.removeprefix('close ') for event in trace.events if event.startswith('close '))
    return opened, closed


def _teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    result = _teardown_call(size, trace)()
    opened, closed = _split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _direct_teardown(size: int, trace: Trace) -> Callable[[], str]:
    members = tuple(_node(index) for index in range(size))

    @contextlib.contextmanager
    def hold(member: type[object]) -> Generator[object]:
        trace.record(member.__name__)
        yield member()
        trace.record(f'close {member.__name__}')

    def run() -> str:
        with contextlib.ExitStack() as stack:
            return _members([stack.enter_context(hold(member)) for member in members])

    return run


def _direct_teardown_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_teardown(size, Trace(recording=False)))


def _direct_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    result = _direct_teardown(size, trace)()
    opened, closed = _split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _async_resource(node: type[object], trace: Trace) -> Callable[..., object]:
    async def make() -> AsyncIterator[object]:
        trace.record(node.__name__)
        yield node()
        trace.record(f'close {node.__name__}')

    make.__annotations__ = {'return': types.GenericAlias(AsyncIterator, (node,))}
    return make


def _async_resources(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = _node(index)
        container = container.bind(_async_resource(member, trace), provides=member, scope=Scope.SCOPED)
        members.append(member)
    return container.collect(Element, members)


def _async_teardown_session(size: int, trace: Trace) -> tuple[Callable[[], str], Callable[[], None]]:
    """One async scope cycle, and the loop release that has to happen outside the timed region."""
    frozen = _async_resources(size, trace).freeze()
    loop = asyncio.new_event_loop()

    async def cycle() -> str:
        async with frozen.ascope():
            return _members(await frozen.aresolve(COLLECTION_KEY))

    return lambda: loop.run_until_complete(cycle()), loop.close


def _async_teardown_prepare(size: int) -> Prepared:
    call, close = _async_teardown_session(size, Trace(recording=False))
    return Prepared(call=call, close=close)


def _async_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    call, close = _async_teardown_session(size, trace)
    try:
        result = call()
    finally:
        close()
    opened, closed = _split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _direct_async_teardown_session(size: int, trace: Trace) -> tuple[Callable[[], str], Callable[[], None]]:
    members = tuple(_node(index) for index in range(size))
    loop = asyncio.new_event_loop()

    @contextlib.asynccontextmanager
    async def hold(member: type[object]) -> AsyncGenerator[object]:
        trace.record(member.__name__)
        yield member()
        trace.record(f'close {member.__name__}')

    async def cycle() -> str:
        async with contextlib.AsyncExitStack() as stack:
            return _members([await stack.enter_async_context(hold(member)) for member in members])

    return lambda: loop.run_until_complete(cycle()), loop.close


def _direct_async_teardown_prepare(size: int) -> Prepared:
    call, close = _direct_async_teardown_session(size, Trace(recording=False))
    return Prepared(call=call, close=close)


def _direct_async_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    call, close = _direct_async_teardown_session(size, trace)
    try:
        result = call()
    finally:
        close()
    opened, closed = _split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _override_nesting_session(size: int) -> tuple[Callable[[], object], Callable[[], None]]:
    """A warm singleton behind `size` nested override frames, none of which name its key.

    The frames are entered in setup and left standing for the whole measurement,
    because entering and leaving them is a different operation from resolving
    through them. Each names a key of its own that nothing binds, so the lookup
    walks the whole stack and then reads the plan — the shape a resolution takes
    inside a test that has overridden something else.
    """
    container, leaf = _chain(OVERRIDE_GRAPH, Scope.SINGLETON, Trace(recording=False))
    frozen = container.freeze()
    _ = frozen.resolve(leaf)
    stack = contextlib.ExitStack()
    try:
        for index in range(size):
            _ = stack.enter_context(frozen.override(type(f'Unrelated{index}', (), {}), object()))
    except BaseException:
        stack.close()
        raise
    return partial(frozen.resolve, leaf), stack.close


def _override_nesting_prepare(size: int) -> Prepared:
    call, close = _override_nesting_session(size)
    return Prepared(call=call, close=close)


def _override_nesting_observe(size: int) -> Observation:
    call, close = _override_nesting_session(size)
    try:
        return Observation(result=type(call()).__name__, constructed=(), closed=())
    finally:
        close()


def _workload(
    name: str,
    size: int,
    claim: Claim,
    subject: tuple[Callable[[int], Prepared], Callable[[int], Observation]],
    baseline: tuple[Callable[[int], Prepared], Callable[[int], Observation]] | None,
) -> Workload:
    return Workload(
        name=f'{name}_{size}',
        tier=Tier.SCALING,
        claim=claim,
        subject=Implementation('depin', partial(subject[0], size), partial(subject[1], size)),
        baseline=(
            None
            if baseline is None
            else Implementation('direct', partial(baseline[0], size), partial(baseline[1], size))
        ),
    )


FREEZE_CLAIM = _claim(
    question='How does validating a graph scale with the number of providers in it?',
    work=(
        'Validate a linear chain of providers into a resolution plan. There is no direct baseline: hand-wiring has '
        'no validation step to compare against, so the curve is read against itself at two sizes rather than against '
        'another implementation.'
    ),
    included='Container.freeze() alone: key canonicalisation, parameter extraction, validation and ordering.',
    excluded='Declaring the bindings, and constructing anything the plan describes.',
    semantics='Every provider is a singleton; nothing is constructed, because freeze() only plans.',
    shape='A chain of n providers, n-1 edges, one root and one leaf.',
    valid=(
        'Whether validation is linear in the size of the graph.',
        'The startup cost a container of a given size adds to a process.',
    ),
    invalid=(
        'Any statement about resolution: nothing is constructed here.',
        'A per-provider cost transferable to another graph shape; a chain is the cheapest shape to order.',
    ),
)

DEPTH_CLAIM = _claim(
    question='How does constructing a dependency chain scale with its depth?',
    work='Construct every node of a transient chain, deepest first, and return the leaf.',
    included='One resolve() of the leaf, and the construction of every node it depends on.',
    excluded='Declaring the bindings and freezing the container.',
    semantics='Every node is transient, so every operation constructs the whole chain and caches nothing.',
    shape='A chain of n providers, n-1 edges.',
    valid=(
        'Whether construction cost is linear in depth.',
        'The overhead depin adds over constructing the same objects by hand, at each depth.',
    ),
    invalid=(
        'The depth a graph may reach: cold resolution recurses, and DEPTH_CLIFF is where it stops.',
        'Anything about a cached lookup, which does not construct.',
    ),
)

FAN_OUT_CLAIM = _claim(
    question='How does resolving one node scale with the number of dependencies it declares?',
    work='Construct n leaves and the single root that declares all of them as parameters.',
    included='One resolve() of the root, and the construction of every leaf.',
    excluded='Declaring the bindings and freezing the container.',
    semantics='Root and leaves are transient, so every operation constructs all n+1 objects.',
    shape='One root with n direct dependencies, depth 2, n edges.',
    valid=(
        'Whether per-parameter cost is linear in the number of parameters.',
        'The overhead depin adds over calling the same constructor with the same arguments.',
    ),
    invalid=(
        'A comparison with the depth curve: the same node count at depth 2 and at depth n are different work.',
        'Anything about a collection, which resolves a list key rather than n parameters.',
    ),
)

COLLECTION_CLAIM = _claim(
    question='How does resolving a collection scale with the number of members in it?',
    work='Construct every member of a collection and return them in registration order.',
    included='One resolve() of the list key, and the construction of every member.',
    excluded='Declaring the bindings and freezing the container.',
    semantics='Members are transient, so every operation constructs a fresh list of fresh members.',
    shape='n independently bound members gathered under one list key, depth 2.',
    valid=(
        'Whether collection cost is linear in member count.',
        'The overhead depin adds over building the same list by hand.',
    ),
    invalid=(
        'Anything about a collection of singletons, whose members are constructed once and then only listed.',
        'Anything about member ordering cost: registration order is the resolution order and is not sorted.',
    ),
)

TEARDOWN_CLAIM = _claim(
    question='How does closing a scope scale with the number of resources opened in it?',
    work='Open a scope, construct n generator-backed resources, and close them in reverse order.',
    included='Scope entry, one resolve() of the collection, and the teardown every resource runs on exit.',
    excluded='Declaring the bindings and freezing the container.',
    semantics='Every member is scoped, so it is constructed once per scope and torn down when that scope closes.',
    shape='n scoped generator providers gathered under one list key.',
    valid=(
        'Whether teardown is linear in the number of resources held.',
        'The overhead depin adds over contextlib.ExitStack over the same generators.',
    ),
    invalid=(
        'Anything about async teardown, which runs on a different path.',
        'Anything about teardown after a failure: this curve measures the path where every resource closes cleanly.',
    ),
)

ASYNC_TEARDOWN_CLAIM = _claim(
    question='How does closing an asynchronous scope scale with the number of resources opened in it?',
    work='Open an async scope, construct n async-generator resources, and close them in reverse order.',
    included=(
        'One run_until_complete of an already created loop, scope entry, one aresolve() of the collection, '
        'and the teardown every resource runs on exit.'
    ),
    excluded='Declaring the bindings, freezing the container, and creating the event loop.',
    semantics='Every member is scoped, so it is constructed once per scope and torn down when that scope closes.',
    shape='n scoped async-generator providers gathered under one list key.',
    valid=(
        'Whether async teardown is linear in the number of resources held.',
        'The overhead depin adds over contextlib.AsyncExitStack over the same async generators.',
    ),
    invalid=(
        'Not comparable with the sync teardown curve as a ratio: the async side carries a loop boundary '
        'the sync side does not, and that boundary is a constant of both implementations here.',
        'Anything about teardown after a failure: this curve measures the path where every resource closes cleanly.',
    ),
)

OVERRIDE_NESTING_CLAIM = _claim(
    question='How does one resolution scale with the number of overrides standing over it?',
    work=(
        'Resolve a warm singleton with n nested override frames active, none of which names the key being '
        'resolved. There is no direct baseline: hand-wiring has no override stack, so the curve is read '
        'against itself at two depths rather than against another implementation.'
    ),
    included=(
        'The whole resolution: the override lookup that walks the n frames, and the cached read it falls through to.'
    ),
    excluded='Declaring the bindings, freezing, entering the override frames, and the first construction.',
    semantics='Singleton, warm before the first timed call. The frames are entered once, in setup, and stand.',
    shape=f'A chain of {OVERRIDE_GRAPH} provider(s) under n nested override frames.',
    valid=(
        'Whether the override stack is walked linearly in its depth rather than worse.',
        'What an override left standing costs every unrelated resolution under it.',
    ),
    invalid=(
        'Not the cost of installing or removing an override, which happens once per frame and is in setup.',
        'Not a per-frame cost read off a single size: the fixed resolution cost sits under the curve, so '
        'each growth ratio understates the linear term rather than isolating it.',
        'Not a realistic nesting depth. The sizes are chosen to put the walk above the fixed cost, not to '
        'describe a test suite, which nests one or two frames.',
    ),
)


def _curve(
    name: str,
    sizes: Sequence[int],
    claim: Claim,
    subject: tuple[Callable[[int], Prepared], Callable[[int], Observation]],
    baseline: tuple[Callable[[int], Prepared], Callable[[int], Observation]] | None = None,
) -> tuple[Workload, ...]:
    return tuple(_workload(name, size, claim, subject, baseline) for size in sizes)


WORKLOADS: tuple[Workload, ...] = (
    *_curve('scale_freeze_graph_size', FREEZE_SIZES, FREEZE_CLAIM, (_freeze_prepare, _freeze_observe)),
    *_curve(
        'scale_resolve_transient_depth',
        DEPTH_SIZES,
        DEPTH_CLAIM,
        (_resolve_prepare, _resolve_observe),
        (_direct_resolve_prepare, _direct_resolve_observe),
    ),
    *_curve(
        'scale_resolve_fan_out',
        FAN_OUT_SIZES,
        FAN_OUT_CLAIM,
        (_fan_out_prepare, _fan_out_observe),
        (_direct_fan_out_prepare, _direct_fan_out_observe),
    ),
    *_curve(
        'scale_resolve_collection',
        COLLECTION_SIZES,
        COLLECTION_CLAIM,
        (_collection_prepare, _collection_observe),
        (_direct_collection_prepare, _direct_collection_observe),
    ),
    *_curve(
        'scale_scope_teardown',
        TEARDOWN_SIZES,
        TEARDOWN_CLAIM,
        (_teardown_prepare, _teardown_observe),
        (_direct_teardown_prepare, _direct_teardown_observe),
    ),
    *_curve(
        'scale_async_teardown',
        ASYNC_TEARDOWN_SIZES,
        ASYNC_TEARDOWN_CLAIM,
        (_async_teardown_prepare, _async_teardown_observe),
        (_direct_async_teardown_prepare, _direct_async_teardown_observe),
    ),
    *_curve(
        'scale_override_nesting',
        OVERRIDE_NESTING_SIZES,
        OVERRIDE_NESTING_CLAIM,
        (_override_nesting_prepare, _override_nesting_observe),
    ),
)


def deepest_resolvable_chain() -> dict[str, int]:
    """Measure the deepest chain a cold `resolve()` survives, by scope.

    The measurement runs in a fresh interpreter, at module level, on the default
    recursion limit. Both are load-bearing: the answer is a frame budget divided by
    `FRAMES_PER_PROVIDER`, so it moves with whatever frames the caller already
    consumed, and a number measured under pytest would pin the test runner's stack
    depth rather than `depin`'s recursion.

    Raises:
        HarnessError: the probe process failed, or printed something other than the
            JSON it is expected to print.
    """
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, '-c', CLIFF_PROBE],
        cwd=root,
        env=os.environ | {'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise HarnessError(f'the depth probe exited {completed.returncode}\n{completed.stderr}')
    try:
        measured: object = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError(f'the depth probe printed {completed.stdout!r}, which is not JSON') from error
    if not is_object(measured):
        raise HarnessError(f'the depth probe printed {completed.stdout!r}, which is not a JSON object')
    deepest = require_object(measured.get('deepest'), 'the depth probe')
    return {scope: require_integer(depth, f'the depth probe: {scope}') for scope, depth in deepest.items()}
