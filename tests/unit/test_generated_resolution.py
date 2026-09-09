import builtins
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import FunctionType, MappingProxyType
from typing import Annotated

import pytest

from depin._core import frozen as frozen_module
from depin._core import generated as generated_module
from depin._core import overrides
from depin._core.container import Container
from depin._core.generated import Program, compile_sync_transients
from depin._core.graph import build_plan
from depin._core.markers import Tag, Token
from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderSpec, ResolutionPlan
from depin.errors import InvalidProviderError


def test_generates_a_single_nested_function_for_a_transient_chain() -> None:
    calls: list[str] = []

    def make_leaf() -> str:
        calls.append('leaf')
        return 'leaf'

    def make_root(user_parameter_name: str) -> list[str]:
        calls.append('root')
        return [user_parameter_name, 'root']

    plan = build_plan(
        Container()
        .bind(make_root, scope=Scope.TRANSIENT, provides=list[str])
        .bind(make_leaf, scope=Scope.TRANSIENT, provides=str)
        .records()
    )

    generated = compile_sync_transients(plan)
    program = generated[(list[str], None)]

    assert isinstance(generated, MappingProxyType)
    assert program() == ['leaf', 'root']
    assert calls == ['leaf', 'root']
    assert isinstance(program, FunctionType)
    assert program.__code__.co_filename == '<depin generated resolver>'
    assert 'user_parameter_name' not in program.__code__.co_names
    assert '_sources' not in program.__globals__
    assert program.__globals__['__builtins__'] == {}


def test_generates_a_twenty_provider_chain_without_recursive_runtime_dispatch() -> None:
    depth = 20
    tokens = [Token[object](f'generated-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        make = _step()
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.TRANSIENT)

    generated = compile_sync_transients(build_plan(container.records()))

    assert generated[(tokens[-1], None)]() == depth


def test_generated_programs_share_one_immutable_provider_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    namespaces: list[tuple[Callable[..., object], ...]] = []

    def capture_namespace(_expression: str, sources: tuple[Callable[..., object], ...]) -> Program:
        namespaces.append(sources)
        return object

    def leaf() -> str:
        return 'value'

    def root(value: str) -> bytes:
        return value.encode()

    plan = build_plan(
        Container()
        .bind(leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )

    monkeypatch.setattr(generated_module, '_program', capture_namespace)
    compile_sync_transients(plan)

    assert len(namespaces) == 2
    assert namespaces[0] is namespaces[1]


def test_generates_tagged_positional_dependencies() -> None:
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

    assert compile_sync_transients(plan)[(bytes, None)]() == b'preferred'


def test_excludes_parameters_that_require_interpreter_call_semantics() -> None:
    default = object()

    def keyword_only(*, value: str) -> bytes:
        return value.encode()

    def with_default(value: object = default) -> bytearray:
        return bytearray(b'default' if value is default else b'changed')

    def with_optional(value: int | None) -> list[int]:
        return [] if value is None else [value]

    plan = build_plan(
        Container()
        .bind(lambda: 'value', provides=str, scope=Scope.TRANSIENT)
        .bind(keyword_only, provides=bytes, scope=Scope.TRANSIENT)
        .bind(with_default, provides=bytearray, scope=Scope.TRANSIENT)
        .bind(with_optional, provides=list[int], scope=Scope.TRANSIENT)
        .records()
    )
    generated = compile_sync_transients(plan)

    assert (bytes, None) not in generated
    assert (bytearray, None) not in generated
    assert (list[int], None) not in generated


def test_excludes_a_keyword_collector_with_a_synthetic_positional_signature() -> None:
    def leaf() -> str:
        return 'value'

    def root(**parts: object) -> bytes:
        return str(parts['value']).encode()

    vars(root)['__signature__'] = inspect.Signature(
        [inspect.Parameter('value', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)],
        return_annotation=bytes,
    )
    root.__annotations__ = {'value': str, 'return': bytes}
    plan = build_plan(
        Container()
        .bind(leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )

    assert (bytes, None) not in compile_sync_transients(plan)


def test_excludes_a_varargs_factory_with_a_synthetic_positional_signature() -> None:
    def leaf() -> str:
        return 'value'

    def root(*values: object) -> bytes:
        return str(values[0]).encode()

    vars(root)['__signature__'] = inspect.Signature(
        [inspect.Parameter('value', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)],
        return_annotation=bytes,
    )
    root.__annotations__ = {'value': str, 'return': bytes}
    plan = build_plan(
        Container()
        .bind(leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )

    assert (bytes, None) not in compile_sync_transients(plan)


def test_excludes_a_synthetic_signature_that_reorders_real_parameters() -> None:
    @dataclass(frozen=True, slots=True)
    class First: ...

    @dataclass(frozen=True, slots=True)
    class Second: ...

    def first() -> First:
        return First()

    def second() -> Second:
        return Second()

    def root(first: First, second: Second) -> tuple[First, Second]:
        return first, second

    vars(root)['__signature__'] = inspect.Signature(
        [
            inspect.Parameter('second', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Second),
            inspect.Parameter('first', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=First),
        ],
        return_annotation=tuple[First, Second],
    )
    plan = build_plan(
        Container()
        .bind(first, scope=Scope.TRANSIENT)
        .bind(second, scope=Scope.TRANSIENT)
        .bind(root, provides=tuple[First, Second], scope=Scope.TRANSIENT)
        .records()
    )

    assert (tuple[First, Second], None) not in compile_sync_transients(plan)


def test_excludes_parameterized_bound_methods() -> None:
    class Root:
        def make(self, value: str) -> bytes:
            return value.encode()

    plan = build_plan(
        Container()
        .bind(lambda: 'value', provides=str, scope=Scope.TRANSIENT)
        .bind(Root().make, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )

    assert (bytes, None) not in compile_sync_transients(plan)


def test_does_not_reinspect_a_validated_factory_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    def value() -> str:
        return 'value'

    plan = build_plan(Container().bind(value, provides=str, scope=Scope.TRANSIENT).records())

    def uninspectable(_factory: Callable[..., object]) -> inspect.Signature:
        raise ValueError('not inspectable')

    monkeypatch.setattr(inspect, 'signature', uninspectable)

    assert compile_sync_transients(plan)[(str, None)]() == 'value'


def test_stops_generation_before_the_source_nesting_limit() -> None:
    depth = 201
    tokens = [Token[object](f'bounded-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        make = _step()
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.TRANSIENT)

    generated = compile_sync_transients(build_plan(container.records()))

    assert (tokens[-2], None) in generated
    assert (tokens[-1], None) not in generated


def test_stops_generation_before_a_shared_dag_expands_exponentially() -> None:
    depth = 16
    tokens = [Token[object](f'shared-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        previous = tokens[index - 1]

        def combine(left: object, right: object) -> object:
            return left if left == right else right

        combine.__annotations__['left'] = previous
        combine.__annotations__['right'] = previous
        container.bind(combine, provides=token, scope=Scope.TRANSIENT)

    generated = compile_sync_transients(build_plan(container.records()))

    assert (tokens[8], None) in generated
    assert (tokens[9], None) not in generated
    assert (tokens[-1], None) not in generated


def test_rejects_a_broken_project_owned_template(monkeypatch: pytest.MonkeyPatch) -> None:
    def value() -> str:
        return 'value'

    def skip_exec(_code: object, _namespace: dict[str, object]) -> None:
        return None

    plan = build_plan(Container().bind(value, provides=str, scope=Scope.TRANSIENT).records())
    monkeypatch.setattr(builtins, 'exec', skip_exec)

    with pytest.raises(InvalidProviderError, match='could not build its generated resolver'):
        compile_sync_transients(plan)


def test_wraps_a_generated_compiler_resource_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def value() -> str:
        return 'value'

    def fail_compile(*_args: object, **_kwargs: object) -> object:
        raise MemoryError('compiler allocation failed')

    plan = build_plan(Container().bind(value, provides=str, scope=Scope.TRANSIENT).records())
    monkeypatch.setattr(builtins, 'compile', fail_compile)

    with pytest.raises(InvalidProviderError, match='could not build its generated resolver') as raised:
        compile_sync_transients(plan)

    assert isinstance(raised.value.__cause__, MemoryError)


@pytest.mark.parametrize(
    ('budget', 'value'),
    [
        ('_MAX_SOURCE_CHARS', 0),
        ('_MAX_TOTAL_EXPANDED_CALLS', 0),
        ('_MAX_TOTAL_SOURCE_CHARS', 0),
    ],
)
def test_skips_generation_when_a_compiler_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
    budget: str,
    value: int,
) -> None:
    def provider() -> str:
        return 'value'

    monkeypatch.setattr(generated_module, budget, value)
    plan = build_plan(Container().bind(provider, provides=str, scope=Scope.TRANSIENT).records())

    assert not compile_sync_transients(plan)


def test_excludes_non_function_cached_and_async_subgraphs() -> None:
    class Constructed: ...

    class Cached: ...

    class AsyncValue: ...

    def cached() -> Cached:
        return Cached()

    def use_cached(value: Cached) -> str:
        return type(value).__name__

    async def async_value() -> AsyncValue:
        return AsyncValue()

    def use_async(value: AsyncValue) -> bytes:
        return type(value).__name__.encode()

    plan = build_plan(
        Container()
        .bind(Constructed, scope=Scope.TRANSIENT)
        .bind(cached, scope=Scope.SINGLETON)
        .bind(use_cached, provides=str, scope=Scope.TRANSIENT)
        .bind(async_value, scope=Scope.TRANSIENT)
        .bind(use_async, provides=bytes, scope=Scope.TRANSIENT)
        .records()
    )
    generated = compile_sync_transients(plan)

    assert (Constructed, None) not in generated
    assert (Cached, None) not in generated
    assert (str, None) not in generated
    assert (AsyncValue, None) not in generated
    assert (bytes, None) not in generated


def test_frozen_container_routes_an_eligible_transient_to_its_generated_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def leaf() -> str:
        calls.append('leaf')
        return 'leaf'

    def root(value: str) -> bytes:
        calls.append('root')
        return value.encode()

    def generated() -> object:
        return b'generated'

    def compile_for_test(_plan: ResolutionPlan) -> Mapping[Ident, Program]:
        return MappingProxyType({(bytes, None): generated})

    monkeypatch.setattr(frozen_module, 'compile_sync_transients', compile_for_test)
    frozen = (
        Container()
        .bind(leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .freeze()
    )

    assert frozen.resolve(bytes) == b'generated'
    assert calls == []


def test_any_active_override_bypasses_generated_program_and_observes_nested_replacements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    unrelated = Token[object]('unrelated')

    def leaf() -> str:
        calls.append('leaf')
        return 'original'

    def root(value: str) -> bytes:
        calls.append('root')
        return value.encode()

    def generated() -> object:
        return b'wrong'

    def compile_for_test(_plan: ResolutionPlan) -> Mapping[Ident, Program]:
        return MappingProxyType({(bytes, None): generated})

    monkeypatch.setattr(frozen_module, 'compile_sync_transients', compile_for_test)
    frozen = (
        Container()
        .bind(leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(root, provides=bytes, scope=Scope.TRANSIENT)
        .value(unrelated, object())
        .freeze()
    )

    assert not overrides.present()
    with frozen.override(unrelated).using(object()):
        assert overrides.present()
        assert frozen.resolve(bytes) == b'original'
        with frozen.override(str).using('replacement'):
            assert overrides.present()
            assert frozen.resolve(bytes) == b'replacement'
        assert overrides.present()
        assert frozen.resolve(bytes) == b'original'
    assert not overrides.present()
    assert calls == ['leaf', 'root', 'root', 'leaf', 'root']


def test_generated_and_interpreted_routes_rebuild_equivalent_transients() -> None:
    calls: list[str] = []
    unrelated = Token[object]('parity')

    @dataclass(frozen=True, slots=True)
    class Leaf:
        serial: int

    @dataclass(frozen=True, slots=True)
    class Result:
        leaf: Leaf

    def leaf() -> Leaf:
        value = Leaf(len(calls))
        calls.append('leaf')
        return value

    def root(value: Leaf) -> Result:
        calls.append('root')
        return Result(value)

    frozen = (
        Container()
        .bind(leaf, scope=Scope.TRANSIENT)
        .bind(root, provides=Result, scope=Scope.TRANSIENT)
        .value(unrelated, object())
        .freeze()
    )

    generated_first = frozen.resolve(Result)
    generated_second = frozen.resolve(Result)
    with frozen.override(unrelated).using(object()):
        interpreted_first = frozen.resolve(Result)
        interpreted_second = frozen.resolve(Result)

    assert type(generated_first) is type(interpreted_first) is Result
    assert [result.leaf.serial for result in (generated_first, generated_second)] == [0, 2]
    assert [result.leaf.serial for result in (interpreted_first, interpreted_second)] == [4, 6]
    results = (generated_first, generated_second, interpreted_first, interpreted_second)
    assert len({id(result) for result in results}) == 4
    assert len({id(result.leaf) for result in results}) == 4
    assert calls == ['leaf', 'root'] * 4


def test_generated_and_interpreted_routes_preserve_factory_exceptions() -> None:
    unrelated = Token[object]('exception-parity')

    def fail() -> str:
        raise LookupError('provider failed')

    frozen = Container().bind(fail, provides=str, scope=Scope.TRANSIENT).value(unrelated, object()).freeze()

    with pytest.raises(LookupError) as generated:
        frozen.resolve(str)
    with frozen.override(unrelated).using(object()), pytest.raises(LookupError) as interpreted:
        frozen.resolve(str)

    assert type(generated.value) is type(interpreted.value)
    assert str(generated.value) == str(interpreted.value) == 'provider failed'


def test_cached_resolution_does_not_read_generated_routing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cached: ...

    value = Cached()
    frozen = Container().value(Token[Cached]('cached'), value).freeze()

    def unexpected_override_read() -> bool:
        raise AssertionError('cached resolution read generated routing state')

    monkeypatch.setattr(overrides, 'present', unexpected_override_read)

    assert frozen.resolve(Token[Cached]('cached')) is value


def test_deep_plan_uses_dense_instructions_without_generated_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth = 1_000
    tokens = [Token[object](f'deep-{index}') for index in range(depth)]
    container = Container()

    def leaf() -> object:
        return 1

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        make = _step()
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.TRANSIENT)

    def unexpected_compile(_plan: ResolutionPlan) -> Mapping[Ident, Program]:
        raise AssertionError('deep plan invoked generated compiler')

    monkeypatch.setattr(frozen_module, 'compile_sync_transients', unexpected_compile)
    frozen = container.freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('eligible deep plan used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    assert frozen.resolve(tokens[-1]) == depth


def _step() -> Callable[[object], object]:
    def make(value: object) -> object:
        if not isinstance(value, int):
            raise TypeError('generated test chain expected an int')
        return value + 1

    return make
