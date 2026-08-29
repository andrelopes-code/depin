"""Static conformance of `Inject[T]`: the parameter's static type is `T` itself."""

from typing import assert_type

from depin.ext.fastapi import Inject


class UserService:
    def name(self) -> str:
        return 'u'


def test_inject_annotates_the_parameter_as_the_service_itself() -> None:
    # The route is nested and never called: a module-level function with an
    # `Inject[...]` parameter would be collected by pytest as a test wanting a
    # fixture named `svc`. `assert_type` is checked statically either way.
    def route(svc: Inject[UserService]) -> str:
        assert_type(svc, UserService)
        return svc.name()

    _ = route
