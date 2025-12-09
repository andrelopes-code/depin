from depin import Container, RequestScopeService, Scope


def test_request_scope_same_instance_within_request():
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.bind(source=A, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        a1 = c.get(A)
        a2 = c.get(A)

    assert a1 is a2
    assert A.call_count == 1


def test_request_scope_different_instances_across_requests():
    c = Container()

    class A: ...

    c.bind(source=A, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        a1 = c.get(A)

    with RequestScopeService.request_scope():
        a2 = c.get(A)

    assert a1 is not a2


def test_request_scope_function_called_once_per_request():
    c = Container()
    call_count = 0

    def provider():
        nonlocal call_count
        call_count += 1
        return call_count

    c.bind(source=provider, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        r1 = c.get(provider)
        r2 = c.get(provider)

    with RequestScopeService.request_scope():
        r3 = c.get(provider)

    assert r1 == r2 == 1
    assert r3 == 2
    assert call_count == 2
