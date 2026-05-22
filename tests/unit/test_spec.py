from dataclasses import FrozenInstanceError

import pytest

from depin._core.scope import Scope
from depin._core.spec import (
    BindRecord,
    ParamSpec,
    ProviderShape,
    ProviderSpec,
    ResolutionPlan,
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
