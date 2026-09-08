from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

import pytest

from depin._core import frozen as frozen_module
from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.instructions import (
    AliasOperation,
    CollectionOperation,
    KeywordOperation,
    Operation,
    ResolvedKeyword,
    SyncTransientProgram,
    compile_sync_transient_instructions,
)
from depin._core.markers import Tag, Token, injected
from depin._core.overrides import present as override_present
from depin._core.scope import Scope
from depin._core.spec import Ident, ParamSpec, ProviderShape, ProviderSpec, ResolutionPlan
from depin.errors import InvalidProviderError


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

    program = compile_sync_transient_instructions(build_plan(container.records()))

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
    program = compile_sync_transient_instructions(plan)

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
    program = compile_sync_transient_instructions(plan)

    assert program.resolve((bytes, None)) == b'preferred'


def test_keeps_unsupported_call_contracts_and_lifetimes_out_of_the_program() -> None:
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
    program = compile_sync_transient_instructions(plan)

    assert not program.operations
    assert not program.roots


def test_compiles_keyword_defaults_optionals_and_classes() -> None:
    class Result:
        def __init__(self, *, count: int, label: str = 'default', payload: bytes | None = None) -> None:
            self.values = (count, label, payload)

    def count() -> int:
        return 7

    plan = build_plan(Container().bind(count, scope=Scope.TRANSIENT).bind(Result, scope=Scope.TRANSIENT).records())
    program = compile_sync_transient_instructions(plan)

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
    program = compile_sync_transient_instructions(plan)

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


def test_preserves_provider_exception_type_and_message() -> None:
    def fail() -> str:
        raise LookupError('instruction provider failed')

    plan = build_plan(Container().bind(fail, provides=str, scope=Scope.TRANSIENT).records())
    program = compile_sync_transient_instructions(plan)

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

    program = compile_sync_transient_instructions(build_plan(container.records()))

    assert program.resolve((tokens[-1], None)) == depth


def test_rejects_a_key_that_has_no_compiled_instruction_root() -> None:
    program = compile_sync_transient_instructions(build_plan(Container().records()))

    with pytest.raises(InvalidProviderError, match='has no synchronous transient instruction program'):
        program.resolve((str, None))


def test_rejects_a_malformed_dependency_slot() -> None:
    operation = Operation(lambda: object(), (1,), (str, None))
    program = SyncTransientProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(
        InvalidProviderError, match='invalid dependency slot 1 in synchronous transient program while resolving str'
    ):
        program.resolve((str, None))


def test_rejects_a_malformed_operation_slot() -> None:
    program = SyncTransientProgram((), MappingProxyType({(str, None): 1}))

    with pytest.raises(InvalidProviderError, match='invalid operation slot 1'):
        program.resolve((str, None))


def test_rejects_a_malformed_keyword_parameter_slot() -> None:
    def accept_keywords(**_kwargs: object) -> object:
        return object()

    operation = KeywordOperation(accept_keywords, (), (ResolvedKeyword('value', 0),), (str, None))
    program = SyncTransientProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match=r'invalid parameter slot 0.*while resolving str'):
        program.resolve((str, None))


def test_rejects_a_malformed_alias_operation() -> None:
    operation = AliasOperation((), (str, None))
    program = SyncTransientProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='alias instruction for str requires exactly one dependency'):
        program.resolve((str, None))


def test_skips_unsupported_shapes_and_required_parameters_without_compiled_dependencies() -> None:
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

    program = compile_sync_transient_instructions(ResolutionPlan((function, value), by_key))

    assert not program.operations


def test_shallow_container_does_not_compile_dense_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
    def value() -> str:
        return 'value'

    def unexpected_compile(_plan: object) -> SyncTransientProgram:
        raise AssertionError('shallow plan invoked the dense instruction compiler')

    monkeypatch.setattr(frozen_module, 'compile_sync_transient_instructions', unexpected_compile)

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
