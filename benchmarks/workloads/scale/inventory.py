"""The ordered inventory of scaling benchmark workloads."""

from collections.abc import Callable, Sequence
from functools import partial

from benchmarks.contracts import Claim, Implementation, Observation, Prepared, Tier, Workload

from .builders import (
    ASYNC_TEARDOWN_SIZES,
    COLLECTION_SIZES,
    DEPTH_SIZES,
    FAN_OUT_SIZES,
    FREEZE_SIZES,
    OVERRIDE_GRAPH,
    OVERRIDE_NESTING_SIZES,
    TEARDOWN_SIZES,
    _claim,
)
from .freeze import (
    _collection_observe,
    _collection_prepare,
    _direct_collection_observe,
    _direct_collection_prepare,
    _direct_fan_out_observe,
    _direct_fan_out_prepare,
    _direct_resolve_observe,
    _direct_resolve_prepare,
    _fan_out_observe,
    _fan_out_prepare,
    _freeze_observe,
    _freeze_prepare,
    _resolve_observe,
    _resolve_prepare,
)
from .override import _override_nesting_observe, _override_nesting_prepare
from .teardown import (
    _async_teardown_observe,
    _async_teardown_prepare,
    _direct_async_teardown_observe,
    _direct_async_teardown_prepare,
    _direct_teardown_observe,
    _direct_teardown_prepare,
    _teardown_observe,
    _teardown_prepare,
)


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
