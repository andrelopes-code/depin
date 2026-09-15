"""Declarative provider discovery preserves exact consumer-visible types.

The seven target shapes each retain their produced value type while their
original callable parameters and protocol wrappers remain usable. Completed
declarations widen covariantly into heterogeneous catalogues, which compose
through nested manifests and enter the ordinary `Bindings` ingestion path.
"""

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Protocol, assert_type

from depin import Bindings, Catalog, Container, Manifest, Provider, Scope, provider, provides


class Dependency: ...


class Contract(Protocol):
    def ready(self) -> bool: ...


class ClassProduct:
    def __init__(self, dependency: Dependency) -> None:
        self.dependency = dependency


class SyncProduct:
    def ready(self) -> bool:
        return True


class CoroutineProduct: ...


class GeneratorProduct: ...


class AsyncGeneratorProduct: ...


class ContextManagerProduct: ...


class AsyncContextManagerProduct: ...


def sync_factory(dependency: Dependency, attempts: int) -> SyncProduct:
    _ = dependency, attempts
    return SyncProduct()


async def coroutine_factory(dependency: Dependency) -> CoroutineProduct:
    _ = dependency
    return CoroutineProduct()


def generator_factory(dependency: Dependency) -> Generator[GeneratorProduct, None, None]:
    _ = dependency
    yield GeneratorProduct()


async def async_generator_factory(dependency: Dependency) -> AsyncGenerator[AsyncGeneratorProduct, None]:
    _ = dependency
    yield AsyncGeneratorProduct()


@contextlib.contextmanager
def context_manager_factory(dependency: Dependency) -> Generator[ContextManagerProduct, None, None]:
    _ = dependency
    yield ContextManagerProduct()


@contextlib.asynccontextmanager
async def async_context_manager_factory(
    dependency: Dependency,
) -> AsyncGenerator[AsyncContextManagerProduct, None]:
    _ = dependency
    yield AsyncContextManagerProduct()


_sync_callable: Callable[[Dependency, int], SyncProduct] = sync_factory
_coroutine_callable: Callable[[Dependency], Awaitable[CoroutineProduct]] = coroutine_factory
_generator_callable: Callable[[Dependency], Generator[GeneratorProduct, None, None]] = generator_factory
_async_generator_callable: Callable[[Dependency], AsyncGenerator[AsyncGeneratorProduct, None]] = async_generator_factory
_context_manager_callable: Callable[[Dependency], AbstractContextManager[ContextManagerProduct]] = (
    context_manager_factory
)
_async_context_manager_callable: Callable[[Dependency], AbstractAsyncContextManager[AsyncContextManagerProduct]] = (
    async_context_manager_factory
)


class_declaration = provider(ClassProduct)
sync_declaration = provider(sync_factory)
coroutine_declaration = provider(coroutine_factory)
generator_declaration = provider(generator_factory)
async_generator_declaration = provider(async_generator_factory)
context_manager_declaration = provider(context_manager_factory)
async_context_manager_declaration = provider(async_context_manager_factory)

assert_type(class_declaration, Provider[ClassProduct])
assert_type(sync_declaration, Provider[SyncProduct])
assert_type(coroutine_declaration, Provider[CoroutineProduct])
assert_type(generator_declaration, Provider[GeneratorProduct])
assert_type(async_generator_declaration, Provider[AsyncGeneratorProduct])
assert_type(context_manager_declaration, Provider[ContextManagerProduct])
assert_type(async_context_manager_declaration, Provider[AsyncContextManagerProduct])


def enabled() -> bool:
    return True


def check_object(value: object) -> bool:
    return value is not None


configured_declaration = sync_declaration.configure(
    scope=Scope.TRANSIENT,
    provides=Contract,
    tag='primary',
    when=enabled,
    check=check_object,
)
assert_type(configured_declaration, Provider[SyncProduct])


@provides(Contract)
class MarkedBefore:
    def ready(self) -> bool:
        return True


before_marker_declaration = provider(MarkedBefore)
assert_type(before_marker_declaration, Provider[MarkedBefore])


class MarkedAfter:
    def ready(self) -> bool:
        return True


after_marker_declaration = provider(MarkedAfter)
marked_after = provides(Contract)(MarkedAfter)
_marked_after_type: type[MarkedAfter] = marked_after
assert_type(after_marker_declaration, Provider[MarkedAfter])


primary_catalog = Catalog(
    __name__,
    class_declaration,
    sync_declaration,
    coroutine_declaration,
    generator_declaration,
    async_generator_declaration,
    context_manager_declaration,
    async_context_manager_declaration,
)
marked_catalog = Catalog(__name__, before_marker_declaration, after_marker_declaration)
assert_type(primary_catalog, Catalog)
assert_type(primary_catalog.providers, tuple[Provider[object], ...])
assert_type(marked_catalog, Catalog)

leaf_manifest = Manifest(__name__, primary_catalog)
manifest = Manifest(__name__, leaf_manifest, marked_catalog)
assert_type(leaf_manifest, Manifest)
assert_type(manifest, Manifest)
assert_type(manifest.sources, tuple[Catalog | Manifest, ...])

_bindings: Bindings = manifest
assert_type(Container(manifest), Container)
assert_type(Container().include(manifest), Container)
