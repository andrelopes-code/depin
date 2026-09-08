# Dense synchronous transient instruction prototype

The prototype compiles each eligible synchronous transient function once into
an immutable operation table. Dependencies are integer indexes. Resolution uses
two local integer stacks and one value stack, so the shared program has no
runtime mutation and repeated transient dependencies are constructed again for
each parameter occurrence.

## Representation growth

Provider callables are excluded because the validated plan already retains
them. The measurement includes the program, operation tuple, operation objects,
dependency tuples, roots mapping proxy, and an equivalent roots dictionary.

| Providers | Operations | Edges | Bytes |
| ---: | ---: | ---: | ---: |
| 20 | 20 | 19 | 2,832 |
| 100 | 100 | 99 | 15,208 |
| 160 | 160 | 159 | 21,448 |
| 1,000 | 1,000 | 999 | 141,072 |

From 20 to 160 providers, the graph grew 8 times while measured storage grew
7.573 times, an exponent of 0.974. The exact operation and edge counts prove
that the representation stores no transitive closure per key.

## Decision diagnostics

Seven-repeat `timeit` medians for a 20-provider transient chain were:

| Route | Median |
| --- | ---: |
| Direct Python | 2.040 µs |
| Generated public `resolve()` | 4.161 µs |
| Dense instruction program | 14.052 µs |
| Interpreted public `resolve()` | 33.465 µs |

The program-only instruction call used 22 Python calls, 12 retained blocks,
1,248 retained bytes, and a 2,064-byte traced peak for one operation. The
interpreted public call used 181 calls, 54 blocks, 4,824 bytes, and a 5,680-byte
peak. These are decision diagnostics rather than replacements for published
paired workload evidence.

At 1,000 providers, the integrated public instruction route measured 724.930
microseconds versus 2,617.506 for the iterative interpreter. Repeated freeze
medians were 36.166 milliseconds with instruction compilation and 34.051
milliseconds without it, a +6.21% cost. The production route is therefore
limited to plans at the existing 256-provider iterative threshold; shallow
plans incur no dense compilation and keep the generated fast path.

The slice is a GO for deep synchronous transient functions. Active overrides,
unsupported call contracts, async resolution, cached/scoped providers, and
resource-owning shapes remain on their existing executors.
