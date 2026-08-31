"""`depin.ext.pytest`, exercised through `pytester` as a real plugin.

A plugin tested by importing its fixture functions and calling them directly
is not tested as a plugin: entry-point registration, fixture visibility with
no `conftest.py` import, and the failure a suite gets when it never defines
`depin_container` are all invisible to that style of test. Every case here
writes a small suite with `pytester.makepyfile` / `makeconftest` and runs it.

A scenario that depends on entry-point registration — nothing here ever
imports `depin.ext.pytest` — runs at least once through
`runpytest_subprocess()`, since an in-process run inherits this suite's
already-loaded plugin and would pass whether or not registration works.
Scenarios about the fixtures' own behaviour additionally run in-process, via
`runpytest()`, so the fixture bodies execute inside this process, where the
coverage collector wrapping this test run can see them; `runpytest_subprocess`
children are invisible to it.
"""

import pytest

pytest_plugins = ['pytester']

_MODES = (pytest.param(True, id='subprocess'), pytest.param(False, id='in-process'))


def _run(pytester: pytest.Pytester, *, subprocess: bool) -> pytest.RunResult:
    return pytester.runpytest_subprocess() if subprocess else pytester.runpytest()


_CLOCK_REPORT_SHAPES = """\
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

_CLOCK_REPORT_CONFTEST = """\
import pytest

from depin import Container, FrozenContainer

from shapes import Report, SystemClock


@pytest.fixture
def depin_container() -> FrozenContainer:
    return Container().bind(SystemClock).bind(Report).freeze()
"""


@pytest.mark.parametrize('subprocess', _MODES)
@pytest.mark.parametrize(
    'test_body',
    [
        pytest.param(
            """\
from shapes import Clock, FakeClock, Report


def test_it(depin_container, depin_override) -> None:
    # Built -- and cached, Report is a singleton -- before the override exists.
    assert depin_container[Report].render() == 'report at real'

    with depin_override(Clock, FakeClock()) as di:
        assert di[Report].render() == 'report at fake'
""",
            id='evicts-a-consumer-built-before-the-block',
        ),
        pytest.param(
            """\
from shapes import Clock, FakeClock, Report


def test_it(depin_container, depin_override) -> None:
    with depin_override(Clock, FakeClock()) as di:
        assert di[Report].render() == 'report at fake'

    assert depin_container[Report].render() == 'report at real'
""",
            id='leaves-nothing-built-inside-the-block',
        ),
    ],
)
def test_override_evicts_and_restores(pytester: pytest.Pytester, test_body: str, subprocess: bool) -> None:
    pytester.makepyfile(shapes=_CLOCK_REPORT_SHAPES)
    pytester.makeconftest(_CLOCK_REPORT_CONFTEST)
    pytester.makepyfile(test_body)

    result = _run(pytester, subprocess=subprocess)

    result.assert_outcomes(passed=1)


def test_override_forwards_tag_to_only_the_tagged_binding(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        shapes="""
        from typing import Protocol


        class Clock(Protocol):
            def now(self) -> str: ...


        class SystemClock:
            def now(self) -> str:
                return 'real'


        class AltClock:
            def now(self) -> str:
                return 'alt-real'


        class FakeClock:
            def now(self) -> str:
                return 'fake'
    """
    )
    pytester.makeconftest("""
        import pytest

        from depin import Container, FrozenContainer

        from shapes import AltClock, Clock, SystemClock


        @pytest.fixture
        def depin_container() -> FrozenContainer:
            return (
                Container()
                .bind(SystemClock, provides=Clock)
                .bind(AltClock, provides=Clock, tag='alt')
                .freeze()
            )
    """)
    pytester.makepyfile("""
        from shapes import Clock, FakeClock


        def test_it(depin_container, depin_override) -> None:
            with depin_override(Clock, FakeClock(), tag='alt') as di:
                assert di.resolve(Clock).now() == 'real'
                assert di.resolve(Clock, tag='alt').now() == 'fake'

            assert depin_container.resolve(Clock, tag='alt').now() == 'alt-real'
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


_GREETER_SHAPES = """\
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

_GREETER_CONFTEST = """\
import pytest

from depin import Container, FrozenContainer

from shapes import Greeting, build_real_greeter


@pytest.fixture
def depin_container() -> FrozenContainer:
    return Container().bind(build_real_greeter).bind(Greeting).freeze()
"""

_GREETER_TEST = """\
from shapes import FakeGreeter, Greeter, Greeting


async def test_it(depin_container, depin_aoverride) -> None:
    real = await depin_container.aresolve(Greeting)
    assert await real.greeter.greet() == 'real'

    async with depin_aoverride(Greeter, FakeGreeter()) as di:
        fake = await di.aresolve(Greeting)
        assert await fake.greeter.greet() == 'fake'

    # The block leaves no trace: the real graph is back once it exits.
    restored = await depin_container.aresolve(Greeting)
    assert await restored.greeter.greet() == 'real'
"""


@pytest.mark.parametrize('subprocess', _MODES)
def test_aoverride_drives_an_async_provider(pytester: pytest.Pytester, subprocess: bool) -> None:
    pytester.makeini('[pytest]\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = function\n')
    pytester.makepyfile(shapes=_GREETER_SHAPES)
    pytester.makeconftest(_GREETER_CONFTEST)
    pytester.makepyfile(_GREETER_TEST)

    result = _run(pytester, subprocess=subprocess)

    result.assert_outcomes(passed=1)


_JOB_CONFTEST = """\
import pytest

from depin import Container, FrozenContainer, Token

job = Token[str]('job')


@pytest.fixture
def depin_container() -> FrozenContainer:
    return Container().scope_value(job).freeze()
"""


@pytest.mark.parametrize('subprocess', _MODES)
def test_depin_scope_hosts_the_container_and_can_be_seeded(pytester: pytest.Pytester, subprocess: bool) -> None:
    pytester.makeconftest(_JOB_CONFTEST)
    pytester.makepyfile("""
        from depin import Token, hosted_container

        job = Token[str]('job')


        def test_it(depin_container, depin_scope) -> None:
            assert hosted_container() is depin_container

            depin_scope.provide(job, 'reindex')

            assert depin_container.resolve(job) == 'reindex'
    """)

    result = _run(pytester, subprocess=subprocess)

    result.assert_outcomes(passed=1)


@pytest.mark.parametrize('subprocess', _MODES)
def test_depin_ascope_hosts_the_container_and_can_be_seeded(pytester: pytest.Pytester, subprocess: bool) -> None:
    pytester.makeini('[pytest]\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = function\n')
    pytester.makeconftest(_JOB_CONFTEST)
    pytester.makepyfile("""
        from depin import Token, hosted_container

        job = Token[str]('job')


        async def test_it(depin_container, depin_ascope) -> None:
            assert hosted_container() is depin_container

            depin_ascope.provide(job, 'reindex')

            assert depin_container.resolve(job) == 'reindex'
    """)

    result = _run(pytester, subprocess=subprocess)

    result.assert_outcomes(passed=1)


_CONTAINER_NOT_DEFINED_TEST = """\
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
"""


@pytest.mark.parametrize('subprocess', _MODES)
def test_missing_depin_container_raises_the_exact_message(pytester: pytest.Pytester, subprocess: bool) -> None:
    pytester.makepyfile(_CONTAINER_NOT_DEFINED_TEST)

    result = _run(pytester, subprocess=subprocess)

    result.assert_outcomes(passed=1)


def test_missing_depin_container_reports_the_fixture_and_its_shape(pytester: pytest.Pytester) -> None:
    """The natural way a user hits this: declaring `depin_container` like any other fixture."""
    pytester.makepyfile("""
        def test_it(depin_container) -> None:
            pass
    """)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        [
            '*depin_container is not defined.*',
            '*Add a fixture to your conftest.py:*',
            '*def depin_container() -> FrozenContainer:*',
            '*return build_container()*',
        ]
    )


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
