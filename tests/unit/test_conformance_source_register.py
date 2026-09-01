"""The source registers, and the comparison the `typing-source` gate makes against them.

The gate itself needs three checkers, three `uvx` downloads and a synced
interpreter, so it is a CI job rather than a commit gate. What is testable here
is the part that decides pass from fail: the register parser, which refuses an
entry the comparison could not act on, and the comparison, which has to fail in
three directions rather than one. A register that only ever grew would record
limitations that no longer exist.
"""

import pytest

from scripts.conformance.model import CHECKOUT, ConformanceError, Diagnostic
from scripts.conformance.source import SOURCE_CHECKS, compare, parse_register, read_register

REGISTERS = [check.register for check in SOURCE_CHECKS if check.register is not None]


@pytest.mark.parametrize('register', REGISTERS)
def test_every_committed_register_parses(register: str) -> None:
    entries = read_register(register)
    assert entries, f'{register} carries no entries'
    for entry in entries:
        assert entry.classification
        assert entry.count >= 1


@pytest.mark.parametrize('register', REGISTERS)
def test_every_registered_file_still_exists(register: str) -> None:
    """An entry naming a deleted file is stale in a way the gate cannot see.

    The gate fails on an entry whose diagnostic no longer appears, but only
    once the checker has run. This is the cheaper half of the same guard.
    """
    for entry in read_register(register):
        assert (CHECKOUT / entry.path).is_file(), f'{register} names {entry.path}, which does not exist'


def test_an_entry_carries_a_path_a_rule_a_count_and_a_classification() -> None:
    [entry] = parse_register('# a comment\n\na/b.py:some-rule:3 why it is tolerated\n', 'register')
    assert (entry.path, entry.rule, entry.count) == ('a/b.py', 'some-rule', 3)
    assert entry.classification == 'why it is tolerated'


@pytest.mark.parametrize(
    ('line', 'reason'),
    [
        ('a/b.py:some-rule:1', 'carries no classification'),
        ('a/b.py:1 classified', 'is not a file:rule:count triple'),
        (':some-rule:1 classified', 'is not a file:rule:count triple'),
        ('a/b.py:some-rule:0 classified', "'0' is not a positive count"),
        ('a/b.py:some-rule:many classified', "'many' is not a positive count"),
    ],
)
def test_a_register_line_the_comparison_could_not_act_on_is_rejected(line: str, reason: str) -> None:
    with pytest.raises(ConformanceError, match=reason):
        _ = parse_register(line + '\n', 'register')


def test_the_same_file_and_rule_may_not_be_registered_twice() -> None:
    contents = 'a/b.py:some-rule:1 first\na/b.py:some-rule:2 second\n'
    with pytest.raises(ConformanceError, match='appears twice'):
        _ = parse_register(contents, 'register')


def diagnostics(*keys: tuple[str, str]) -> list[Diagnostic]:
    return [Diagnostic(path, index, rule) for index, (path, rule) in enumerate(keys, start=1)]


def test_the_registered_counts_matching_exactly_is_the_only_pass() -> None:
    entries = parse_register('a/b.py:some-rule:2 classified\n', 'register')
    assert compare('ty', 'register', entries, diagnostics(('a/b.py', 'some-rule'), ('a/b.py', 'some-rule'))) == []


@pytest.mark.parametrize(
    ('observed', 'detail'),
    [
        ([('a/b.py', 'some-rule')], 'a count moves in either direction'),
        ([('a/b.py', 'some-rule')] * 3, 'a count moves in either direction'),
        ([], 'and none appears'),
    ],
)
def test_a_registered_count_that_moved_fails(observed: list[tuple[str, str]], detail: str) -> None:
    entries = parse_register('a/b.py:some-rule:2 classified\n', 'register')
    [failure] = compare('ty', 'register', entries, diagnostics(*observed))
    assert detail in failure.detail


def test_a_diagnostic_no_entry_carries_fails() -> None:
    entries = parse_register('a/b.py:some-rule:1 classified\n', 'register')
    observed = diagnostics(('a/b.py', 'some-rule'), ('a/c.py', 'other-rule'))
    [failure] = compare('ty', 'register', entries, observed)
    assert 'a/c.py: 1 other-rule that register does not carry' in failure.detail


def test_a_windows_path_separator_matches_the_registered_posix_path() -> None:
    entries = parse_register('a/b.py:some-rule:1 classified\n', 'register')
    assert compare('ty', 'register', entries, [Diagnostic('a\\b.py', 1, 'some-rule')]) == []
