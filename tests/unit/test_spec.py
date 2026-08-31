from dataclasses import FrozenInstanceError

import pytest

from depin._core.scope import Scope
from depin._core.spec import (
    AliasBinding,
    BindRecord,
    CollectionBinding,
    ParamSpec,
    ProviderShape,
    ProviderSpec,
    ResolutionPlan,
    collection_key,
    collection_param,
    fmt_chain,
    fmt_key,
    is_alias_binding,
)


def test_provider_shape_members() -> None:
    expected = {
        'CLASS',
        'FUNCTION',
        'ASYNC_FUNCTION',
        'GENERATOR',
        'ASYNC_GENERATOR',
        'CONTEXT_MANAGER',
        'ASYNC_CONTEXT_MANAGER',
        'VALUE',
        'FRAME',
        'ALIAS',
        'COLLECTION',
    }
    assert {s.name for s in ProviderShape} == expected


def test_bind_record_is_immutable() -> None:
    class A: ...

    rec = BindRecord(source=A, scope=Scope.SINGLETON, provides=None, tag=None)
    with pytest.raises(FrozenInstanceError):
        setattr(rec, 'scope', Scope.TRANSIENT)  # noqa: B010


def test_param_spec_round_trip() -> None:
    class B: ...

    p = ParamSpec(name='b', key=B, tag=None, has_default=False, default=None)
    assert p.name == 'b'
    assert p.key is B


def test_resolution_plan_lookup() -> None:
    class C: ...

    spec = ProviderSpec(
        key=C,
        tag=None,
        source=C,
        scope=Scope.SINGLETON,
        shape=ProviderShape.CLASS,
        needs_async=False,
        params=(),
    )
    plan = ResolutionPlan(order=(spec,), by_key={(C, None): spec})
    assert plan.by_key[(C, None)] is spec


def test_fmt_chain_joins_keys_with_arrows() -> None:
    class First: ...

    class Second: ...

    assert fmt_chain([First, Second]) == f'{fmt_key(First)} -> {fmt_key(Second)}'


def test_fmt_chain_of_one_key_has_no_arrow() -> None:
    class Only: ...

    assert fmt_chain([Only]) == fmt_key(Only)


def test_fmt_chain_of_nothing_is_empty() -> None:
    assert fmt_chain([]) == ''


def test_alias_binding_is_immutable() -> None:
    class Store: ...

    binding = AliasBinding(key=Store, target=Store, target_tag=None)
    with pytest.raises(FrozenInstanceError):
        setattr(binding, 'target_tag', 'x')  # noqa: B010


def test_is_alias_binding_narrows_only_alias_bindings() -> None:
    class Store: ...

    assert is_alias_binding(AliasBinding(key=Store, target=Store, target_tag=None))
    assert not is_alias_binding(Store)


def test_collection_binding_is_immutable() -> None:
    class Handler: ...

    binding = CollectionBinding(element=Handler, members=(Handler,))
    with pytest.raises(FrozenInstanceError):
        setattr(binding, 'members', ())  # noqa: B010


def test_collection_key_is_a_list_of_the_element() -> None:
    class Handler: ...

    assert collection_key(Handler) == list[Handler]


def test_collection_params_are_distinct_and_ordered() -> None:
    assert [collection_param(index) for index in range(3)] == ['member_0', 'member_1', 'member_2']


def test_fmt_key_renders_a_collection_key_by_qualified_name() -> None:
    class Handler: ...

    assert fmt_key(list[Handler]) == f'list[{fmt_key(Handler)}]'


def test_fmt_key_leaves_a_union_alone() -> None:
    class Cache: ...

    class Logger: ...

    assert fmt_key(Cache | Logger) == repr(Cache | Logger)
