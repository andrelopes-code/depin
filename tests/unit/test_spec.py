from dataclasses import FrozenInstanceError

import pytest

from depin._core.scope import Scope
from depin._core.spec import (
    BindRecord,
    ParamSpec,
    ProviderShape,
    ProviderSpec,
    ResolutionPlan,
    fmt_chain,
    fmt_key,
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
