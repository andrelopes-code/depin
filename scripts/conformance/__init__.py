"""Run the consumer typing conformance suite: five checkers, one built wheel.

The corpus under `conformance/` is ordinary consumer code. It is checked against
the wheel this repository builds, installed into interpreters that have never
heard of the checkout, in a core-only and an all-extras mode.

Two properties make the result mean something, and both are structural rather
than incidental.

The first is where the checkers run. Invoked from the repository root, mypy
resolves ``depin`` out of the checkout even when the interpreter it was pointed
at has no ``depin`` installed at all, and reports success. The working directory
is therefore as much a leak as ``PYTHONPATH`` is. This runner copies
`conformance/` into a temporary directory outside the checkout and gives every
checker subprocess that directory as its working directory, asserting for each
one that the checkout is neither the working directory nor an ancestor of it.
The guard is on the subprocess, never on this process: ``uv run python -m
scripts.conformance`` runs from the checkout by definition.

The second is the empty-interpreter control. Each checker runs the identical
command line, from the identical directory, against an interpreter with no
``depin``, and must report an unresolved import. That is a positive assertion
about behaviour rather than an enumeration of the variables that could leak, so
it catches a stray ``.pth``, an ``extraPaths`` entry, a ``MYPYPATH`` or a
working directory however it arrived.

Usage:
    uv run python -m scripts.conformance [--checker NAME] [--mode core|extras]
                                         [--only STAGE]

| Module | Responsibility |
| --- | --- |
| `model.py` | The shared data structures, the error type, and TOML/JSON narrowing. |
| `pins.py` | `checkers.toml`, the `uv.lock` lockstep check, and the corpus import ban. |
| `workspace.py` | The wheel, the three interpreters, the copied corpus, and every subprocess. |
| `isolation.py` | The assertions that run before any checking. |
| `checkers.py` | One command builder and one output parser per checker. |
| `stages.py` | The control, positive, anti-erasure and negative stages. |
| `cli.py` | Argument parsing, the table, and the exit status. |
"""

from scripts.conformance.cli import main

__all__ = ('main',)
