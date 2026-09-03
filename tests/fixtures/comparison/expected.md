# Comparative performance evidence

## allocations_of_a_cached_singleton_resolution

| Measure | Result |
| --- | --- |
| Claim | What does one resolution allocate once the value is already built? |
| Status | leader |
| Noise allowance | 1.0% |
| Direct overhead | +500.000 ms |
| Absolute target | 1.000 s |
| Secondary verdict | allocations: pass, work: pass |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | same observed cached resolution | 1.000 s | 900.000 ms | [-10.00%, -10.00%] |
| dishka-1.10.1 | partial | does not preserve the complete observation | — | — | — |
| wireup-2.12.0 | incomparable | cannot express this cache lifecycle | — | — | — |

## Provenance

| Property | Value |
| --- | --- |
| Source revision | head-revision |
| Harness revision | harness-revision |
| Dependency versions | dependency-injector 4.49.1, pydepin 0.17.1 |
| Host | synthetic-system synthetic-machine synthetic-cpu |
| Collection command | python -m benchmarks.harness.comparison collect --repetitions 5 |
