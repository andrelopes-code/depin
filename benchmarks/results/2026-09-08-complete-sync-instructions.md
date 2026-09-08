# Complete synchronous instruction calls

This slice broadens the accepted dense transient program from exact positional
functions to the complete teardown-free synchronous call matrix. Immutable
keyword slots distinguish resolved dependencies, omitted Python defaults, and
unbound optional values. Dedicated operations cover classes, aliases, and
collections; decorators compile through the same class/function operations as
their rewritten graph nodes.

An active override selects the iterative executor after one root-level override
state read. A live scope also selects the iterative executor when any operation
in the requested subgraph has an unbound default or optional parameter, because
the scope may supply that otherwise-unbound key. Both fallbacks preserve the
existing nested lookup semantics.

## Representation growth

The richer keyword-chain measurement includes the program, operation and roots
containers, operation objects, dependency tuples, keyword tuples and slot
objects, the frame-sensitive set, and an equivalent mutable roots dictionary.
Provider callables remain excluded because the validated plan already retains
them.

| Providers | Operations | Edges | Keyword slots | Bytes |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 20 | 19 | 19 | 5,192 |
| 100 | 100 | 99 | 99 | 26,528 |
| 160 | 160 | 159 | 159 | 39,488 |
| 1,000 | 1,000 | 999 | 999 | 253,192 |

From 20 to 160 providers the graph grew eight times and measured storage grew
7.606 times, an exponent of 0.976. Each provider still contributes one
operation, and each dependency contributes one integer edge and at most one
argument slot; the representation stores no transitive schedule per root.

## Decision diagnostics

Seven-repeat `timeit` medians compared this slice with `c7c83de`, the accepted
positional-only dense runtime. A 256-provider keyword-only transient chain moved
from the iterative executor to dense instructions and improved from 704.564 to
430.698 microseconds (-38.87%). A 256-node plan with one transient dependency
and a keyword-only class carrying default and optional parameters improved from
7.361 to 4.974 microseconds (-32.43%).

The already-accepted 1,000-provider positional chain measured 605.414
microseconds at `c7c83de` and 637.035 microseconds after restoring its
specialized zero/one/many-argument loop (+5.22%). This remains below the normal
10% regression boundary and well below the original 2,617.506-microsecond
iterative result. Freezing a 1,000-provider keyword chain moved from 41.382 to
43.525 milliseconds (+5.18%). These figures are design diagnostics, not new
published workload budgets.

## Correctness evidence

Nineteen focused tests cover positional and keyword functions, keyword-only
classes, defaults, optionals, tags, repeated transients, aliases, ordered
collections, rewritten decorators, provider exception parity, 1,000-node depth,
active overrides, scope-provided unbound values, single root-level override
state reads, stable dependency-chain diagnostics, and malformed instruction
slots. The broader alias, collection, decorator, optional, generated, and
iterative suites pass 131 tests together.

Direct branch coverage of `depin/_core/instructions.py` executes all 166
statements and reports 99% branch coverage; the two partial arcs are structural
exits from exhaustive pattern matches. The complete repository suite passes
2,599 tests with 6 skipped before the documentation-only decision update.

This slice is a GO. Cached and scoped claims remain on the existing executor
until their synchronization phase; resource-owning and asynchronous shapes
remain reserved for their dedicated phases.
