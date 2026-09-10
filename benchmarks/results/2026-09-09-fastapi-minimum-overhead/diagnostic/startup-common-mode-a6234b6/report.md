# Corrected FastAPI startup diagnostic

Compared base `086adf98459773e3175f4723b2b64e3f47306e42` with head `a6234b6f5dadbfe0fab09829201cce120699d28f` after the common-route correction. Five counterbalanced repetitions ran in AB, BA, AB, BA, AB order, pinned to CPUs `0-3` with `PYTHONHASHSEED=0`.

Each process invoked:

```text
uv run --group bench pytest benchmarks/test_comparison.py -k fastapi_application_startup --benchmark-only -q --benchmark-json=<rep>.json
```

Each direct and depin case recorded 1,000 rounds with one iteration.

| Rep | Base direct p50 | Base depin p50 | Head direct p50 | Head depin p50 | Base attributable | Head attributable | Attributable increment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1671.964 us | 2557.727 us | 1721.201 us | 2792.419 us | 885.763 us | 1071.219 us | 185.456 us |
| 1 | 1662.781 us | 2589.109 us | 1619.384 us | 2668.530 us | 926.329 us | 1049.146 us | 122.817 us |
| 2 | 1683.256 us | 2603.747 us | 1714.499 us | 2808.124 us | 920.491 us | 1093.625 us | 173.134 us |
| 3 | 1710.053 us | 2603.766 us | 1637.352 us | 2791.784 us | 893.713 us | 1154.432 us | 260.719 us |
| 4 | 1666.520 us | 2475.220 us | 1621.836 us | 2628.272 us | 808.700 us | 1006.436 us | 197.736 us |

The per-pair total depin relative changes have median `+7.221%`. A seeded 20,000-resample paired bootstrap of that median gives a 95% interval of `[+3.067%, +9.176%]`.

Median DI-attributable startup is `893.713 us` on base and `1071.219 us` on head: an increment of `177.506 us` when subtracting the median direct p50s. The median paired attributable increment is `185.456 us`; the median paired attributable relative change is `+20.937%`.

The corrected workload removes the earlier comparability failure, but the total startup upper confidence bound remains above the `+6%` budget. This supports performing the fused hidden-name traversal before formal recollection.
