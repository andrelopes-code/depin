from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, TypeGuard

import pytest

from depin._core.compiled import compile_sync_transients
from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.graph import build_plan
from depin._core.markers import Tag, Token
from depin._core.scope import Scope


def test_compiles_a_transient_function_chain_in_dependency_order() -> None:
    calls: list[str] = []

    def make_leaf() -> str:
        calls.append('leaf')
        return 'leaf'

    def make_root(leaf: str) -> list[str]:
        calls.append('root')
        return [leaf, 'root']

    plan = (
        Container()
        .bind(make_root, scope=Scope.TRANSIENT, provides=list[str])
        .bind(make_leaf, scope=Scope.TRANSIENT, provides=str)
    )
    compiled = compile_sync_transients(build_plan(plan.records()))

    assert isinstance(compiled, MappingProxyType)
    assert compiled[(list[str], None)]() == ['leaf', 'root']
    assert calls == ['leaf', 'root']


def test_excludes_transient_functions_with_cached_or_scoped_dependencies() -> None:
    class SingletonDependency: ...

    class ScopedDependency: ...

    def make_singleton() -> SingletonDependency:
        return SingletonDependency()

    def make_scoped() -> ScopedDependency:
        return ScopedDependency()

    def use_singleton(dependency: SingletonDependency) -> str:
        return 'singleton'

    def use_scoped(dependency: ScopedDependency) -> bytes:
        return b'scoped'

    plan = (
        Container()
        .bind(make_singleton, scope=Scope.SINGLETON)
        .bind(make_scoped, scope=Scope.SCOPED)
        .bind(use_singleton, scope=Scope.TRANSIENT, provides=str)
        .bind(use_scoped, scope=Scope.TRANSIENT, provides=bytes)
    )
    compiled = compile_sync_transients(build_plan(plan.records()))

    assert (str, None) not in compiled
    assert (bytes, None) not in compiled


def test_excludes_transient_classes_and_async_resolution_paths() -> None:
    class Constructed: ...

    class AsyncDependency: ...

    async def make_async_dependency() -> AsyncDependency:
        return AsyncDependency()

    def use_async_dependency(dependency: AsyncDependency) -> str:
        return 'async'

    plan = (
        Container()
        .bind(Constructed, scope=Scope.TRANSIENT)
        .bind(make_async_dependency, scope=Scope.TRANSIENT)
        .bind(use_async_dependency, scope=Scope.TRANSIENT, provides=str)
    )
    compiled = compile_sync_transients(build_plan(plan.records()))

    assert (Constructed, None) not in compiled
    assert (AsyncDependency, None) not in compiled
    assert (str, None) not in compiled


def test_frozen_container_uses_compiled_program_without_an_active_override() -> None:
    compiled_calls: list[str] = []
    interpreted_calls: list[str] = []

    class Result:
        def __init__(self, value: str) -> None:
            self.value = value

    def make_compiled_leaf() -> str:
        compiled_calls.append('leaf')
        return 'leaf'

    def make_compiled_root(leaf: str) -> Result:
        compiled_calls.append('root')
        return Result(f'{leaf}:root')

    def make_interpreted_leaf() -> str:
        interpreted_calls.append('leaf')
        return 'leaf'

    def make_interpreted_root(leaf: str) -> Result:
        interpreted_calls.append('root')
        return Result(f'{leaf}:root')

    compiled = (
        Container()
        .bind(make_compiled_leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(make_compiled_root, provides=Result, scope=Scope.TRANSIENT)
        .value(Token[object]('unrelated'), object())
        .freeze()
    )
    interpreted = (
        Container()
        .bind(make_interpreted_leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(make_interpreted_root, provides=Result, scope=Scope.TRANSIENT)
        .value(Token[object]('unrelated'), object())
        .freeze()
    )

    assert (Result, None) in _sync_transients(compiled)
    assert compiled.resolve(Result).value == 'leaf:root'
    with interpreted.override(Token[object]('unrelated')).using(object()):
        assert interpreted.resolve(Result).value == 'leaf:root'
    assert compiled_calls == interpreted_calls == ['leaf', 'root']


def test_active_override_of_nested_dependency_bypasses_compiled_program() -> None:
    calls: list[str] = []

    def make_leaf() -> str:
        calls.append('leaf')
        return 'original'

    def make_root(leaf: str) -> bytes:
        calls.append('root')
        return leaf.encode()

    frozen = (
        Container()
        .bind(make_leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(make_root, provides=bytes, scope=Scope.TRANSIENT)
        .freeze()
    )

    assert (bytes, None) in _sync_transients(frozen)
    with frozen.override(str).using('replacement'):
        assert frozen.resolve(bytes) == b'replacement'
    assert calls == ['root']


def test_large_transient_plan_keeps_iterative_executor_and_no_compiled_programs() -> None:
    depth = 1_000
    tokens = [Token[object](f'node-{index}') for index in range(depth)]
    terminal = object()
    container = Container()

    def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):
        make = _step()
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.TRANSIENT)

    frozen = container.freeze()

    assert not _sync_transients(frozen)
    assert frozen.resolve(tokens[-1]) is terminal


def _step() -> Callable[[object], object]:
    def make(value: object) -> object:
        return value

    return make


def test_defaults_optional_parameters_and_frame_values_remain_interpreted() -> None:
    default = object()

    def with_default(value: object = default) -> bytes:
        return b'default' if value is default else b'changed'

    def with_optional(value: str | None) -> bytearray:
        return bytearray(b'none' if value is None else value.encode())

    frozen = (
        Container()
        .bind(with_default, provides=bytes)
        .bind(with_optional, provides=bytearray, scope=Scope.TRANSIENT)
        .freeze()
    )

    assert (bytes, None) not in _sync_transients(frozen)
    assert (bytearray, None) not in _sync_transients(frozen)
    assert frozen.resolve(bytes) == b'default'
    assert frozen.resolve(bytearray) == bytearray(b'none')
    with frozen.scope() as frame:
        frame.provide(str, 'frame')
        assert frozen.resolve(bytearray) == bytearray(b'frame')


@dataclass(frozen=True)
class _Resolved:
    values: tuple[object, ...]


@dataclass(frozen=True)
class _Leaf:
    label: str


@pytest.mark.parametrize('shape', ['zero', 'one', 'multiple', 'tagged'])
def test_compiled_transient_resolution_matches_interpreted_resolution(shape: str) -> None:
    compiled_calls: list[str] = []
    interpreted_calls: list[str] = []
    compiled = _transient_container(shape, compiled_calls)
    interpreted = _transient_container(shape, interpreted_calls)

    compiled_result = compiled.resolve(_Resolved)
    with interpreted.override(Token[object]('unrelated')).using(object()):
        interpreted_result = interpreted.resolve(_Resolved)

    assert type(compiled_result) is type(interpreted_result)
    assert compiled_result == interpreted_result
    assert compiled_calls == interpreted_calls


def test_compiled_transient_factory_exception_matches_interpreted_resolution() -> None:
    compiled_calls: list[str] = []
    interpreted_calls: list[str] = []
    compiled = _failing_transient_container(compiled_calls)
    interpreted = _failing_transient_container(interpreted_calls)

    with pytest.raises(_FactoryFailure) as compiled_error:
        compiled.resolve(_Resolved)
    with (
        interpreted.override(Token[object]('unrelated')).using(object()),
        pytest.raises(_FactoryFailure) as interpreted_error,
    ):
        interpreted.resolve(_Resolved)

    assert type(compiled_error.value) is type(interpreted_error.value)
    assert str(compiled_error.value) == str(interpreted_error.value)
    assert compiled_calls == interpreted_calls == ['leaf', 'root']


def test_nested_unrelated_overrides_keep_compiled_and_interpreted_results_equivalent() -> None:
    compiled_calls: list[str] = []
    interpreted_calls: list[str] = []
    outer = Token[object]('outer')
    inner = Token[object]('inner')
    compiled = _transient_container('multiple', compiled_calls)
    interpreted = _transient_container('multiple', interpreted_calls)

    compiled_result = compiled.resolve(_Resolved)
    with interpreted.override(outer).using(object()), interpreted.override(inner).using(object()):
        interpreted_result = interpreted.resolve(_Resolved)

    assert type(compiled_result) is type(interpreted_result)
    assert compiled_result == interpreted_result
    assert compiled_calls == interpreted_calls


def test_repeated_compiled_and_interpreted_transient_resolution_rebuilds_every_value() -> None:
    compiled_calls: list[str] = []
    interpreted_calls: list[str] = []
    compiled = _identity_transient_container(compiled_calls)
    interpreted = _identity_transient_container(interpreted_calls)

    compiled_first = compiled.resolve(_Resolved)
    compiled_second = compiled.resolve(_Resolved)
    with interpreted.override(Token[object]('unrelated')).using(object()):
        interpreted_first = interpreted.resolve(_Resolved)
        interpreted_second = interpreted.resolve(_Resolved)

    assert type(compiled_first) is type(interpreted_first)
    assert compiled_first == interpreted_first
    assert type(compiled_second) is type(interpreted_second)
    assert compiled_second == interpreted_second
    assert compiled_first is not compiled_second
    assert interpreted_first is not interpreted_second
    assert compiled_first.values[0] is not compiled_second.values[0]
    assert interpreted_first.values[0] is not interpreted_second.values[0]
    assert compiled_calls == interpreted_calls == ['leaf', 'root', 'leaf', 'root']


class _FactoryFailure(Exception):
    pass


def _transient_container(shape: str, calls: list[str]) -> FrozenContainer:
    unrelated = Token[object]('unrelated')

    if shape == 'zero':

        def make_zero_root() -> _Resolved:
            calls.append('root')
            return _Resolved(('root',))

        return (
            Container()
            .bind(make_zero_root, provides=_Resolved, scope=Scope.TRANSIENT)
            .value(unrelated, object())
            .freeze()
        )

    if shape == 'one':

        def make_leaf() -> str:
            calls.append('leaf')
            return 'leaf'

        def make_one_root(leaf: str) -> _Resolved:
            calls.append('root')
            return _Resolved((leaf, 'root'))

        return (
            Container()
            .bind(make_leaf, provides=str, scope=Scope.TRANSIENT)
            .bind(make_one_root, provides=_Resolved, scope=Scope.TRANSIENT)
            .value(unrelated, object())
            .freeze()
        )

    if shape == 'multiple':

        def make_text() -> str:
            calls.append('text')
            return 'text'

        def make_number() -> int:
            calls.append('number')
            return 7

        def make_multiple_root(text: str, number: int) -> _Resolved:
            calls.append('root')
            return _Resolved((text, number))

        return (
            Container()
            .bind(make_text, provides=str, scope=Scope.TRANSIENT)
            .bind(make_number, provides=int, scope=Scope.TRANSIENT)
            .bind(make_multiple_root, provides=_Resolved, scope=Scope.TRANSIENT)
            .value(unrelated, object())
            .freeze()
        )

    if shape == 'tagged':

        def make_leaf() -> str:
            calls.append('leaf')
            return 'tagged'

        def make_tagged_root(leaf: Annotated[str, Tag('primary')]) -> _Resolved:
            calls.append('root')
            return _Resolved((leaf, 'root'))

        return (
            Container()
            .bind(make_leaf, provides=str, tag='primary', scope=Scope.TRANSIENT)
            .bind(make_tagged_root, provides=_Resolved, scope=Scope.TRANSIENT)
            .value(unrelated, object())
            .freeze()
        )

    raise AssertionError(f'unknown transient shape: {shape}')


def _failing_transient_container(calls: list[str]) -> FrozenContainer:
    unrelated = Token[object]('unrelated')

    def make_leaf() -> str:
        calls.append('leaf')
        return 'leaf'

    def make_root(leaf: str) -> _Resolved:
        calls.append('root')
        raise _FactoryFailure(f'cannot use {leaf}')

    return (
        Container()
        .bind(make_leaf, provides=str, scope=Scope.TRANSIENT)
        .bind(make_root, provides=_Resolved, scope=Scope.TRANSIENT)
        .value(unrelated, object())
        .freeze()
    )


def _identity_transient_container(calls: list[str]) -> FrozenContainer:
    unrelated = Token[object]('unrelated')

    def make_leaf() -> _Leaf:
        calls.append('leaf')
        return _Leaf('leaf')

    def make_root(leaf: _Leaf) -> _Resolved:
        calls.append('root')
        return _Resolved((leaf,))

    return (
        Container()
        .bind(make_leaf, provides=_Leaf, scope=Scope.TRANSIENT)
        .bind(make_root, provides=_Resolved, scope=Scope.TRANSIENT)
        .value(unrelated, object())
        .freeze()
    )


def _sync_transients(frozen: object) -> Mapping[object, object]:
    value = frozen.__getattribute__('_sync_transients')
    if _is_object_mapping(value):
        return value
    raise AssertionError('FrozenContainer must store its compiled transient programs as a mapping')


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)
