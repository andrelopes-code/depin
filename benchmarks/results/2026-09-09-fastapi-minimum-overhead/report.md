# FastAPI minimum-overhead collection status

This directory is not an accepted before/after collection. The required
five-repetition collection was stopped after its first counterbalanced pair
because the CPU-light diagnostic could not plausibly satisfy the proposal's
25% reduction requirement.

Raw aggregates are retained in `base/rep0.json` and `head/rep0.json`. The
collector was interrupted before deterministic measurements and the second
counterbalanced pair, so this report intentionally does not present confidence
intervals, memory, allocation, startup, contention, or gate verdicts.

See `analysis.md` for the measured falsifiable diagnosis and `environment.json`
for collection provenance.
