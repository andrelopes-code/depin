import threading
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Protocol, runtime_checkable

import pytest

from depin._core import frozen as frozen_module
from depin._core import instructions as instructions_module
from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.instructions import (
    AliasOperation,
    CollectionOperation,
    ContextManagerOperation,
    FrameOperation,
    GeneratorOperation,
    InstructionReady,
    InstructionStart,
    KeywordOperation,
    Operation,
    ResolvedKeyword,
    StructuredOperation,
    SyncInstructionProgram,
    ValueOperation,
    compile_operation,
    compile_sync_instructions,
    invoke_structured,
)
from depin._core.markers import Tag, Token, injected
from depin._core.overrides import present as override_present
from depin._core.scope import Scope, ScopeFrame
from depin._core.spec import Ident, ParamSpec, ProviderShape, ProviderSpec, ResolutionPlan
from depin._core.teardown import Teardown
from depin.errors import CircularDependencyError, DepinError, InvalidProviderError, MissingProviderError


def test_compiles_one_linear_operation_table_for_every_transient_root() -> None:
    depth = 20
    tokens = [Token[object](f'instruction-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        step = _step()
        step.__annotations__['value'] = tokens[index - 1]
        container.bind(step, provides=token, scope=Scope.TRANSIENT)

    program = compile_sync_instructions(build_plan(container.records()))

    assert isinstance(program.operations, tuple)
    assert isinstance(program.roots, MappingProxyType)
    assert len(program.operations) == depth
    assert len(program.roots) == depth
    assert sum(len(operation.dependencies) for operation in program.operations) == depth - 1
    assert program.resolve((tokens[-1], None)) == depth


def test_rebuilds_repeated_transient_dependencies_without_memoizing_them() -> None:
    @dataclass(frozen=True, slots=True)
    class Leaf:
        serial: int

    calls: list[str] = []
    pairs: list[tuple[Leaf, Leaf]] = []

    def leaf() -> Leaf:
        value = Leaf(len(calls))
        calls.append('leaf')
        return value

    def root(left: Leaf, right: Leaf) -> bytes:
        calls.append('root')
        pairs.append((left, right))
        return b'result'

    plan = build_plan(
        Container().bind(leaf, scope=Scope.TRANSIENT).bind(root, provides=bytes, scope=Scope.TRANSIENT).records()
    )
    program = compile_sync_instructions(plan)

    assert program.resolve((bytes, None)) == b'result'
    assert program.resolve((bytes, None)) == b'result'

    first, second = pairs
    assert first[0] is not first[1]
    assert second[0] is not second[1]
    assert {leaf.serial for leaf in (*first, *second)} == {0, 1, 3, 4}
    assert calls == ['leaf', 'leaf', 'root'] * 2


def test_resolves_tagged_dependencies_by_integer_slot() -> None:
    def preferred() -> str:
        return 'preferred'

    def root(value: Annotated[str, Tag('preferred')]) -> bytes:
        return value.encode()

    plan = build_plan(
        Container()
        .bind(preferred, provides=str, tag='preferred', scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )
    program = compile_sync_instructions(plan)

    assert program.resolve((bytes, None)) == b'preferred'


def test_keeps_async_call_contracts_out_of_the_program_and_compiles_cached_dependencies() -> None:
    async def async_value() -> str:
        return 'async'

    def cached() -> int:
        return 1

    def uses_cached(value: int) -> bytes:
        return str(value).encode()

    plan = build_plan(
        Container()
        .bind(async_value, provides=str, scope=Scope.TRANSIENT)
        .bind(cached, provides=int, scope=Scope.SINGLETON)
        .bind(uses_cached, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )
    program = compile_sync_instructions(plan)

    assert not program.supports((str, None))
    assert program.supports((int, None))
    assert program.supports((bytes, None))


def test_compiles_keyword_defaults_optionals_and_classes() -> None:
    class Result:
        def __init__(self, *, count: int, label: str = 'default', payload: bytes | None = None) -> None:
            self.values = (count, label, payload)

    def count() -> int:
        return 7

    plan = build_plan(Container().bind(count, scope=Scope.TRANSIENT).bind(Result, scope=Scope.TRANSIENT).records())
    program = compile_sync_instructions(plan)

    assert isinstance(program.operations[-1], KeywordOperation)
    result = program.resolve((Result, None))
    assert isinstance(result, Result)
    assert result.values == (7, 'default', None)


def test_compiles_aliases_collections_and_decorators() -> None:
    class Service:
        def __init__(self, labels: tuple[str, ...]) -> None:
            self.labels = labels

    class Alias: ...

    class Element: ...

    class Second: ...

    first_value = Element()
    second_value = Second()

    def service() -> Service:
        return Service(('inner',))

    def decorate(inner: Service, *, suffix: str = 'outer') -> Service:
        return Service((*inner.labels, suffix))

    def element() -> Element:
        return first_value

    def second() -> Second:
        return second_value

    plan = build_plan(
        Container()
        .bind(service, scope=Scope.TRANSIENT)
        .decorate(Service, decorate)
        .bind(element, scope=Scope.TRANSIENT)
        .bind(second, scope=Scope.TRANSIENT)
        .alias(Alias, to=Element)
        .collect(Element, [Alias, Second])
        .records()
    )
    program = compile_sync_instructions(plan)

    assert isinstance(program.operations[program.roots[(Alias, None)]], AliasOperation)
    assert isinstance(program.operations[program.roots[(list[Element], None)]], CollectionOperation)
    decorated = program.resolve((Service, None))
    collection = program.resolve((list[Element], None))
    assert isinstance(decorated, Service)
    assert isinstance(collection, list)
    assert decorated.labels == ('inner', 'outer')
    assert collection == [first_value, second_value]


def test_deep_keyword_root_uses_instructions_outside_a_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        def __init__(self, *, value: int, missing: bytes | None = None) -> None:
            self.values = (value, missing)

    container = Container()
    for index in range(254):
        container.value(Token[int](f'keyword-padding-{index}'), index)

    def value() -> int:
        return 9

    frozen = container.bind(value, scope=Scope.TRANSIENT).bind(Result, scope=Scope.TRANSIENT).freeze()
    override_state_reads = 0
    read_override_state = override_present

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep keyword root used the interpreted executor')

    def count_override_state_reads() -> bool:
        nonlocal override_state_reads
        override_state_reads += 1
        return read_override_state()

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)
    monkeypatch.setattr('depin._core.frozen.overrides.present', count_override_state_reads)

    result = frozen.resolve(Result)
    assert result.values == (9, None)
    assert override_state_reads == 1


def test_active_scope_falls_back_when_it_can_supply_an_unbound_parameter() -> None:
    class Result:
        def __init__(self, value: str | None) -> None:
            self.value = value

    class Outer:
        def __init__(self, result: Result) -> None:
            self.value = result.value

    container = Container()
    for index in range(254):
        container.value(Token[int](f'scope-padding-{index}'), index)
    frozen = container.bind(Result, scope=Scope.TRANSIENT).bind(Outer, scope=Scope.TRANSIENT).freeze()

    assert frozen.resolve(Outer).value is None
    with frozen.scope() as frame:
        frame.provide(str, 'from scope')
        assert frozen.resolve(Outer).value == 'from scope'


def test_deep_singleton_chain_uses_instructions_for_cold_and_warm_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth = 256
    tokens = [Token[object](f'singleton-instruction-{index}') for index in range(depth)]
    terminal = object()
    container = Container()

    def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.SINGLETON)
    for index, token in enumerate(tokens[1:], start=1):
        step = _pass_through(tokens[index - 1])
        container.bind(step, provides=token, scope=Scope.SINGLETON)
    frozen = container.freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep singleton root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    assert frozen.resolve(tokens[-1]) is terminal
    assert frozen.resolve(tokens[-1]) is terminal


def test_deep_scoped_chain_uses_instructions_and_caches_per_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    depth = 256
    tokens = [Token[object](f'scoped-instruction-{index}') for index in range(depth)]
    calls = 0
    container = Container()

    def leaf() -> object:
        nonlocal calls
        calls += 1
        return object()

    container.bind(leaf, provides=tokens[0], scope=Scope.SCOPED)
    for index, token in enumerate(tokens[1:], start=1):
        step = _pass_through(tokens[index - 1])
        container.bind(step, provides=token, scope=Scope.SCOPED)
    frozen = container.freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep scoped root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    with frozen.scope():
        first = frozen.resolve(tokens[-1])
        assert frozen.resolve(tokens[-1]) is first
    with frozen.scope():
        second = frozen.resolve(tokens[-1])
        assert frozen.resolve(tokens[-1]) is second
    assert first is not second
    assert calls == 2


def test_transient_instruction_root_reuses_a_singleton_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    root = Token[tuple[object]]('mixed-lifetime-root')
    container = Container()
    for index in range(254):
        container.value(Token[int](f'mixed-lifetime-padding-{index}'), index)

    def singleton() -> object:
        nonlocal calls
        calls += 1
        return object()

    def transient(value: object) -> tuple[object]:
        return (value,)

    frozen = (
        container.bind(singleton, scope=Scope.SINGLETON).bind(transient, provides=root, scope=Scope.TRANSIENT).freeze()
    )

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('mixed-lifetime root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    first = frozen.resolve(root)
    second = frozen.resolve(root)
    assert first is not second
    assert first[0] is second[0]
    assert calls == 1


def test_deep_instruction_reads_a_scope_value_and_preserves_its_missing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Request: ...

    class Report:
        def __init__(self, request: Request) -> None:
            self.request = request

    container = Container()
    for index in range(254):
        container.value(Token[int](f'frame-padding-{index}'), index)
    frozen = container.scope_value(Request).bind(Report, scope=Scope.TRANSIENT).freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('scope-value root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    request = Request()
    with frozen.scope() as frame:
        frame.provide(Request, request)
        assert frozen.resolve(Report).request is request
    with (
        frozen.scope(),
        pytest.raises(
            MissingProviderError,
            match=r'no value in the active scope for .*Request.*a key declared with scope_value\(\)',
        ),
    ):
        frozen.resolve(Report)


def test_failed_instruction_claim_is_aborted_and_retried() -> None:
    attempts = 0
    container = Container()
    for index in range(255):
        container.value(Token[int](f'failure-padding-{index}'), index)

    def unstable() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LookupError('instruction singleton failed')
        return 'recovered'

    frozen = container.bind(unstable, provides=str, scope=Scope.SINGLETON).freeze()

    with pytest.raises(LookupError, match='instruction singleton failed'):
        frozen.resolve(str)
    assert frozen.resolve(str) == 'recovered'
    assert attempts == 2


@runtime_checkable
class _InstructionBegin(Protocol):
    def begin(self, scope: Scope, ident: Ident, claims: list[object | None]) -> InstructionStart: ...


@runtime_checkable
class _InstructionControl(_InstructionBegin, Protocol):
    def publish(self, claim: object, value: object) -> None: ...

    def abort(self, claim: object) -> None: ...


def _instruction_control() -> _InstructionControl:
    container = Container()
    for index in range(256):
        container.value(Token[int](f'instruction-control-{index}'), index)
    frozen = container.freeze()
    runtime = object.__getattribute__(frozen, '_instruction_runtime')
    if not isinstance(runtime, _InstructionControl):
        raise AssertionError('frozen container has no controllable instruction runtime')
    return runtime


def test_instruction_runtime_rejects_invalid_claims_and_ignores_released_claims() -> None:
    runtime = _instruction_control()

    with pytest.raises(DepinError, match='invalid cache claim'):
        runtime.publish(object(), object())
    with pytest.raises(DepinError, match='invalid cache claim'):
        runtime.abort(object())

    claims: list[object | None] = []
    started = runtime.begin(Scope.SINGLETON, (str, None), claims)
    assert not started.ready
    assert started.value is None
    runtime.abort(started)
    runtime.abort(started)
    runtime.publish(started, object())


def test_instruction_runtime_aborts_a_claim_when_publication_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _instruction_control()
    claims: list[object | None] = []
    started = runtime.begin(Scope.SINGLETON, (str, None), claims)

    def fail_publish(
        _frame: ScopeFrame,
        _key: object,
        _leader: object,
        _value: object,
        *,
        signal: bool = False,
    ) -> None:
        del signal
        raise LookupError('cache publication failed')

    monkeypatch.setattr(ScopeFrame, 'publish', fail_publish)

    with pytest.raises(LookupError, match='cache publication failed'):
        runtime.publish(started, object())


def test_interrupted_instruction_start_aborts_its_registered_claim_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    container = Container()
    for index in range(255):
        container.value(Token[int](f'interrupted-start-padding-{index}'), index)

    def singleton() -> str:
        nonlocal calls
        calls += 1
        return 'recovered'

    frozen = container.bind(singleton, provides=str, scope=Scope.SINGLETON).freeze()
    runtime = object.__getattribute__(frozen, '_instruction_runtime')
    if not isinstance(runtime, _InstructionBegin):
        raise AssertionError('frozen container has no instruction runtime')
    original_begin = runtime.begin
    interrupted = False

    def interrupt_after_claim(
        _runtime: _InstructionBegin,
        scope: Scope,
        ident: Ident,
        claims: list[object | None],
    ) -> InstructionStart:
        nonlocal interrupted
        started = original_begin(scope, ident, claims)
        if not started.ready and not interrupted:
            interrupted = True
            raise KeyboardInterrupt('interrupt after instruction claim')
        return started

    monkeypatch.setattr(type(runtime), 'begin', interrupt_after_claim)

    with pytest.raises(KeyboardInterrupt, match='interrupt after instruction claim'):
        frozen.resolve(str)
    assert frozen.resolve(str) == 'recovered'
    assert calls == 1


def test_recursive_instruction_claim_keeps_the_actionable_error() -> None:
    frozen: frozen_module.FrozenContainer
    container = Container()
    for index in range(255):
        container.value(Token[int](f'recursive-padding-{index}'), index)

    def recursive() -> str:
        return frozen.resolve(str)

    frozen = container.bind(recursive, provides=str, scope=Scope.SINGLETON).freeze()

    with pytest.raises(
        CircularDependencyError,
        match=(
            r'^str is already constructing in this context; '
            r'resolve a different dependency or break the recursive provider call$'
        ),
    ):
        frozen.resolve(str)


class _SyncWaiter(Protocol):
    def wait_sync(self) -> None: ...


def test_concurrent_instruction_claim_single_flights_one_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    start = threading.Barrier(3)
    entered = threading.Event()
    follower_waiting = threading.Event()
    release = threading.Event()
    calls = 0
    value = object()
    results: list[object] = []
    failures: list[BaseException] = []
    container = Container()
    for index in range(255):
        container.value(Token[int](f'concurrent-padding-{index}'), index)

    def singleton() -> object:
        nonlocal calls
        calls += 1
        entered.set()
        if not release.wait(2):
            raise RuntimeError('instruction concurrency test did not release the provider')
        return value

    frozen = container.bind(singleton, scope=Scope.SINGLETON).freeze()

    def observe_wait(_frame: ScopeFrame, waiter: _SyncWaiter) -> None:
        follower_waiting.set()
        waiter.wait_sync()

    def resolve() -> None:
        try:
            start.wait()
            results.append(frozen.resolve(object))
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(ScopeFrame, 'wait_sync', observe_wait)

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('concurrent singleton root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)
    threads = [threading.Thread(target=resolve) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    assert entered.wait(2)
    assert follower_waiting.wait(2)
    release.set()
    for thread in threads:
        thread.join(2)

    assert not failures
    assert results == [value, value]
    assert calls == 1


def test_interrupted_instruction_publish_aborts_and_wakes_a_follower(monkeypatch: pytest.MonkeyPatch) -> None:
    start = threading.Barrier(3)
    entered = threading.Event()
    follower_waiting = threading.Event()
    interrupted = threading.Event()
    calls = 0
    value = object()
    results: list[object] = []
    interruptions: list[KeyboardInterrupt] = []
    failures: list[BaseException] = []
    container = Container()
    for index in range(255):
        container.value(Token[int](f'interrupted-publish-padding-{index}'), index)

    def singleton() -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            if not follower_waiting.wait(2):
                raise RuntimeError('instruction publish test found no waiting follower')
        return value

    frozen = container.bind(singleton, scope=Scope.SINGLETON).freeze()
    original_publish = ScopeFrame.publish

    def observe_wait(_frame: ScopeFrame, waiter: _SyncWaiter) -> None:
        follower_waiting.set()
        waiter.wait_sync()

    def interrupt_first_publish(
        frame: ScopeFrame,
        key: object,
        leader: object,
        resolved: object,
        *,
        signal: bool = False,
    ) -> object:
        if not interrupted.is_set():
            interrupted.set()
            raise KeyboardInterrupt('interrupt before instruction publish')
        return original_publish(frame, key, leader, resolved, signal=signal)

    def resolve() -> None:
        try:
            start.wait()
            try:
                resolved = frozen.resolve(object)
            except KeyboardInterrupt as exc:
                interruptions.append(exc)
                resolved = frozen.resolve(object)
            results.append(resolved)
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(ScopeFrame, 'wait_sync', observe_wait)
    monkeypatch.setattr(ScopeFrame, 'publish', interrupt_first_publish)
    threads = [threading.Thread(target=resolve) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    assert entered.wait(2)
    for thread in threads:
        thread.join(2)

    assert all(not thread.is_alive() for thread in threads)
    assert not failures
    assert len(interruptions) == 1
    assert results == [value, value]
    assert calls == 2


def test_preserves_provider_exception_type_and_message() -> None:
    def fail() -> str:
        raise LookupError('instruction provider failed')

    plan = build_plan(Container().bind(fail, provides=str, scope=Scope.TRANSIENT).records())
    program = compile_sync_instructions(plan)

    with pytest.raises(LookupError, match='instruction provider failed'):
        program.resolve((str, None))


def test_resolves_one_thousand_operations_without_python_recursion() -> None:
    depth = 1_000
    tokens = [Token[object](f'deep-instruction-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        step = _step()
        step.__annotations__['value'] = tokens[index - 1]
        container.bind(step, provides=token, scope=Scope.TRANSIENT)

    program = compile_sync_instructions(build_plan(container.records()))

    assert program.resolve((tokens[-1], None)) == depth


def test_rejects_a_key_that_has_no_compiled_instruction_root() -> None:
    program = compile_sync_instructions(build_plan(Container().records()))

    with pytest.raises(InvalidProviderError, match='has no synchronous instruction program'):
        program.resolve((str, None))


def test_rejects_a_malformed_dependency_slot() -> None:
    operation = Operation(lambda: object(), (1,), (str, None))
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(
        InvalidProviderError, match='invalid dependency slot 1 in synchronous instruction program while resolving str'
    ):
        program.resolve((str, None))


def test_rejects_a_malformed_operation_slot() -> None:
    program = SyncInstructionProgram((), MappingProxyType({(str, None): 1}))

    with pytest.raises(InvalidProviderError, match='invalid operation slot 1'):
        program.resolve((str, None))


class _ReadySyncRuntime:
    def begin(self, scope: Scope, ident: Ident, claims: list[object | None]) -> InstructionStart:
        del scope, ident, claims
        return InstructionReady('cached')

    def publish(self, claim: object, value: object) -> None:
        del claim, value

    def abort(self, claim: object) -> None:
        del claim

    def read_frame(self, ident: Ident) -> object:
        del ident
        return object()

    def register_teardown(self, scope: Scope, record: Teardown) -> None:
        del scope, record


def test_returns_a_ready_cached_instruction_without_calling_its_factory() -> None:
    def unexpected() -> object:
        raise AssertionError('cached instruction called its factory')

    operation = Operation(unexpected, (), (str, None), Scope.SINGLETON)
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    assert program.resolve((str, None), _ReadySyncRuntime()) == 'cached'


def test_cached_instruction_requires_a_runtime() -> None:
    operation = Operation(lambda: object(), (), (str, None), Scope.SINGLETON)
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='requires a cache runtime'):
        program.resolve((str, None))


def test_rejects_a_claim_that_completes_without_a_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def start_with_claim(
        _operation: object,
        _runtime: object,
        claims: list[object | None],
    ) -> None:
        claims.append(object())

    monkeypatch.setattr(instructions_module, '_start', start_with_claim)
    operation = Operation(lambda: object(), (), (str, None))
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='cached instruction completed without a runtime'):
        program.resolve((str, None))


def test_an_empty_operation_chain_has_no_diagnostic_suffix() -> None:
    program = SyncInstructionProgram((), MappingProxyType({}))
    render_chain = object.__getattribute__(program, '_chain')
    if not callable(render_chain):
        raise AssertionError('instruction program has no chain renderer')

    assert render_chain([]) == ''


def test_multi_parameter_operation_stops_when_a_positional_dependency_is_not_compiled() -> None:
    def combine(first: int, second: bytes) -> str:
        return f'{first}:{second!r}'

    first = ParamSpec(name='first', key=int, tag=None, has_default=False, default=None)
    second = ParamSpec(name='second', key=bytes, tag=None, has_default=False, default=None)
    spec = ProviderSpec(
        key=str,
        tag=None,
        source=combine,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.FUNCTION,
        needs_async=False,
        params=(first, second),
    )
    by_key: dict[Ident, ProviderSpec] = {(str, None): spec, (bytes, None): spec}
    plan = ResolutionPlan((spec,), MappingProxyType(by_key))

    assert compile_operation(spec, plan, {(int, None): 0}) is None


def test_rejects_a_malformed_keyword_parameter_slot() -> None:
    def accept_keywords(**_kwargs: object) -> object:
        return object()

    operation = KeywordOperation(accept_keywords, (), (ResolvedKeyword('value', 0),), (str, None))
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match=r'invalid parameter slot 0.*while resolving str'):
        program.resolve((str, None))


def test_rejects_a_malformed_alias_operation() -> None:
    operation = AliasOperation((), (str, None))
    program = SyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='alias instruction for str requires exactly one dependency'):
        program.resolve((str, None))


@pytest.mark.parametrize(
    'operation',
    [
        FrameOperation((), (str, None), Scope.SCOPED),
        GeneratorOperation(lambda: object(), (), (), (str, None), Scope.SINGLETON),
        ContextManagerOperation(lambda: object(), (), (), (str, None), Scope.SINGLETON),
    ],
)
def test_runtime_owned_structured_operations_require_a_runtime(operation: StructuredOperation) -> None:
    with pytest.raises(InvalidProviderError, match=r'requires a (?:frame|resource) runtime'):
        invoke_structured(operation, [], None)


def test_skips_required_parameters_without_compiled_dependencies_and_compiles_values() -> None:
    def stringify(value: object) -> str:
        return str(value)

    required = ParamSpec(name='value', key=int, tag=None, has_default=False, default=None)
    function = ProviderSpec(
        key=str,
        tag=None,
        source=stringify,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.FUNCTION,
        needs_async=False,
        params=(required,),
    )
    value = ProviderSpec(
        key=bytes,
        tag=None,
        source=b'value',
        scope=Scope.TRANSIENT,
        shape=ProviderShape.VALUE,
        needs_async=False,
        params=(),
    )
    mutable_by_key: dict[Ident, ProviderSpec] = {(str, None): function, (bytes, None): value}
    by_key = MappingProxyType(mutable_by_key)

    program = compile_sync_instructions(ResolutionPlan((function, value), by_key))

    assert len(program.operations) == 1
    assert isinstance(program.operations[0], ValueOperation)
    assert not program.supports((str, None))
    assert program.supports((bytes, None))


def test_shallow_container_does_not_compile_dense_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
    def value() -> str:
        return 'value'

    def unexpected_compile(_plan: object) -> SyncInstructionProgram:
        raise AssertionError('shallow plan invoked the dense instruction compiler')

    monkeypatch.setattr(frozen_module, 'compile_sync_instructions', unexpected_compile)

    assert Container().bind(value, provides=str, scope=Scope.TRANSIENT).freeze().resolve(str) == 'value'


def test_active_override_bypasses_a_deep_instruction_program() -> None:
    depth = 256
    tokens = [Token[object](f'override-instruction-{index}') for index in range(depth)]
    original = object()
    replacement = object()
    container = Container()

    def leaf() -> object:
        return original

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        previous = tokens[index - 1]

        def pass_through(value: object) -> object:
            return value

        pass_through.__annotations__['value'] = previous
        container.bind(pass_through, provides=token, scope=Scope.TRANSIENT)

    frozen = container.freeze()

    assert frozen.resolve(tokens[-1]) is original
    with frozen.override(tokens[0]).using(replacement):
        assert frozen.resolve(tokens[-1]) is replacement


def test_sync_inject_uses_a_deep_instruction_program(monkeypatch: pytest.MonkeyPatch) -> None:
    depth = 256
    tokens = [Token[object](f'injected-instruction-{index}') for index in range(depth)]
    terminal = object()
    container = Container()

    def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        previous = tokens[index - 1]

        def pass_through(value: object) -> object:
            return value

        pass_through.__annotations__['value'] = previous
        container.bind(pass_through, provides=token, scope=Scope.TRANSIENT)

    frozen = container.freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('sync inject used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    @frozen.inject
    def handler(value: Annotated[object, tokens[-1]] = injected) -> object:
        return value

    assert handler() is terminal


def _step() -> Callable[[object], object]:
    def step(value: object) -> object:
        if not isinstance(value, int):
            raise TypeError('instruction test chain expected an int')
        return value + 1

    return step


def _pass_through(dependency: Token[object]) -> Callable[[object], object]:
    def pass_through(value: object) -> object:
        return value

    pass_through.__annotations__['value'] = dependency
    return pass_through
