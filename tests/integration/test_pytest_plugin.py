"""`depin.ext.pytest`, exercised through `pytester` as a real plugin.

A plugin tested by importing its fixture functions and calling them directly
is not tested as a plugin: entry-point registration, fixture visibility with
no `conftest.py` import, and the failure a suite gets when it never defines
`depin_container` are all invisible to that style of test. Every case here
writes a small suite with `pytester.makepyfile` / `makeconftest` and runs it
with `runpytest_subprocess()`, so an in-process run cannot inherit this
suite's already-loaded plugin and pass regardless of whether registration
works.
"""

import pytest

pytest_plugins = ['pytester']


def test_missing_depin_container_raises_naming_the_fixture_and_its_shape(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        import pytest

        from depin.errors import ContainerNotBoundError


        def test_it(request: pytest.FixtureRequest) -> None:
            with pytest.raises(ContainerNotBoundError) as exc_info:
                request.getfixturevalue('depin_container')
            assert str(exc_info.value) == (
                'depin_container is not defined.\\n'
                'Add a fixture to your conftest.py:\\n\\n'
                '    @pytest.fixture\\n'
                '    def depin_container() -> FrozenContainer:\\n'
                '        return build_container()\\n'
            )
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_a_conftest_defined_container_needs_no_plugin_import(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer, Token

        greeting = Token[str]('greeting')


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return Container().value(greeting, 'hi').freeze()
    """)
    pytester.makepyfile("""
        from depin import Token

        greeting = Token[str]('greeting')


        def test_it(depin_container) -> None:
            assert depin_container.resolve(greeting) == 'hi'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_override_evicts_a_consumer_built_before_the_block(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        shapes="""
        from typing import Protocol

        from depin import provides


        class Clock(Protocol):
            def now(self) -> str: ...


        @provides(Clock)
        class SystemClock:
            def now(self) -> str:
                return 'real'


        class FakeClock:
            def now(self) -> str:
                return 'fake'


        class Report:
            def __init__(self, clock: Clock) -> None:
                self.clock = clock

            def render(self) -> str:
                return f'report at {self.clock.now()}'
    """
    )
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer

        from shapes import Report, SystemClock


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return Container().bind(SystemClock).bind(Report).freeze()
    """)
    pytester.makepyfile("""
        from shapes import Clock, FakeClock, Report


        def test_it(depin_container, depin_override) -> None:
            # Built — and cached, Report is a singleton — before the override exists.
            assert depin_container[Report].render() == 'report at real'

            with depin_override(Clock, FakeClock()) as di:
                assert di[Report].render() == 'report at fake'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_override_leaves_nothing_built_inside_the_block(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        shapes="""
        from typing import Protocol

        from depin import provides


        class Clock(Protocol):
            def now(self) -> str: ...


        @provides(Clock)
        class SystemClock:
            def now(self) -> str:
                return 'real'


        class FakeClock:
            def now(self) -> str:
                return 'fake'


        class Report:
            def __init__(self, clock: Clock) -> None:
                self.clock = clock

            def render(self) -> str:
                return f'report at {self.clock.now()}'
    """
    )
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer

        from shapes import Report, SystemClock


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return Container().bind(SystemClock).bind(Report).freeze()
    """)
    pytester.makepyfile("""
        from shapes import Clock, FakeClock, Report


        def test_it(depin_container, depin_override) -> None:
            with depin_override(Clock, FakeClock()) as di:
                assert di[Report].render() == 'report at fake'

            assert depin_container[Report].render() == 'report at real'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_aoverride_drives_an_async_provider(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        asyncio_mode = auto
    """)
    pytester.makepyfile(
        shapes="""
        from typing import Protocol


        class Greeter(Protocol):
            async def greet(self) -> str: ...


        class RealGreeter:
            async def greet(self) -> str:
                return 'real'


        class FakeGreeter:
            async def greet(self) -> str:
                return 'fake'


        async def build_real_greeter() -> Greeter:
            return RealGreeter()


        class Greeting:
            def __init__(self, greeter: Greeter) -> None:
                self.greeter = greeter
    """
    )
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer

        from shapes import Greeting, build_real_greeter


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return Container().bind(build_real_greeter).bind(Greeting).freeze()
    """)
    pytester.makepyfile("""
        from shapes import FakeGreeter, Greeter, Greeting


        async def test_it(depin_container, depin_aoverride) -> None:
            real = await depin_container.aresolve(Greeting)
            assert await real.greeter.greet() == 'real'

            async with depin_aoverride(Greeter, FakeGreeter()) as di:
                fake = await di.aresolve(Greeting)
                assert await fake.greeter.greet() == 'fake'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_depin_scope_hosts_the_container_and_can_be_seeded(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer, Token

        job = Token[str]('job')


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return Container().scope_value(job).freeze()
    """)
    pytester.makepyfile("""
        from depin import Token, hosted_container

        job = Token[str]('job')


        def test_it(depin_container, depin_scope) -> None:
            assert hosted_container() is depin_container

            depin_scope.provide(job, 'reindex')

            assert depin_container.resolve(job) == 'reindex'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
