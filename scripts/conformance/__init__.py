"""Run the typing conformance suite: five checkers over two objects.

The corpus under `conformance/` is ordinary consumer code. It is checked against
the wheel this repository builds, installed into interpreters that have never
heard of the checkout, in a core-only and an all-extras mode.

``--source`` checks the other object, the repository's own code, where stock
Pyright runs at zero and ty and Pyrefly run against a committed register. That
layer needs no wheel and no interpreter of its own, so it skips everything the
next two paragraphs describe.

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
                                         [--only STAGE] [--pin CHECKER=VERSION]
                                         [--target-python VERSION]
    uv run python -m scripts.conformance --source [--checker NAME]

| Module | Responsibility |
| --- | --- |
| `model.py` | The shared data structures, the error type, and TOML/JSON narrowing. |
| `pins.py` | `checkers.toml`, the `uv.lock` lockstep check, and the corpus import ban. |
| `workspace.py` | The wheel, the three interpreters, the copied corpus, and every subprocess. |
| `isolation.py` | The assertions that run before any checking. |
| `checkers.py` | One command builder and one output parser per checker. |
| `stages.py` | The control, positive, anti-erasure, negative and divergence stages. |
| `source.py` | The Layer 1 gate over the repository source, and the registers behind it. |
| `cli.py` | Argument parsing, the table, and the exit status. |
"""

from scripts.conformance.cli import main

__all__ = ('main',)
