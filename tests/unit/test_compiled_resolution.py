from types import MappingProxyType

from depin._core.compiled import compile_sync_transients
from depin._core.graph import build_plan
from depin._core.registry import Registry
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
        Registry()
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
        Registry()
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
        Registry()
        .bind(Constructed, scope=Scope.TRANSIENT)
        .bind(make_async_dependency, scope=Scope.TRANSIENT)
        .bind(use_async_dependency, scope=Scope.TRANSIENT, provides=str)
    )
    compiled = compile_sync_transients(build_plan(plan.records()))

    assert (Constructed, None) not in compiled
    assert (AsyncDependency, None) not in compiled
    assert (str, None) not in compiled
