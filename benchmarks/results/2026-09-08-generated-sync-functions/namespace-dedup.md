# Generated namespace deduplication

Revision under test shared one final provider tuple across every generated
program. The measurement counts each unique function object, defaults tuple,
code object, and provider namespace tuple once with `sys.getsizeof`; provider
callables are excluded because the validated plan already retains them.

| Providers | Namespaces | Namespace bytes | Function/default bytes | Code bytes | Total bytes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 1 | 200 | 4,160 | 7,760 | 12,120 |
| 100 | 1 | 840 | 20,800 | 110,800 | 132,440 |
| 160 | 1 | 1,320 | 33,280 | 263,680 | 298,280 |

From 20 to 160 providers, graph size grew 8 times while executable storage
grew 24.611 times, an exponent of 1.540. From 100 to 160 it grew 2.252 times
for 1.6 times as many providers, an exponent of 1.727. Namespace sharing
therefore removes tuple duplication but does not make the representation
linear; nested code remains duplicated for every resolvable root.

A one-run diagnostic after the change measured the generated transient chain
at 4.589 microseconds. Freeze medians were 384.496 microseconds at 10 providers,
3.538 milliseconds at 100, and 36.842 milliseconds at 1,000. These diagnostics
are decision support, not replacements for the retained paired dataset.
