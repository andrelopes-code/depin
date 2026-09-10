# Competitor collection provenance

Candidate source revision: `4f798bec90b5222427254a659052a94b511c3e00`.
Measured FastAPI runtime/workload revision remains
`bb10ef98d8d46b41563d2b6e42ee903b35d53fba`; this candidate packages evidence
only.

Baseline archive was materialized outside a Git worktree using:

```sh
git archive 086adf98459773e3175f4723b2b64e3f47306e42 | tar -x -C "$BASELINE_DIR"
printf '%s\n' 086adf98459773e3175f4723b2b64e3f47306e42 > "$BASELINE_DIR/.depin-baseline-revision"
```

The collector ran from the clean detached candidate source with
`UV_PROJECT_ENVIRONMENT=/tmp/depin-task5-competitor-env` and
`UV_CACHE_DIR=/tmp/depin-task5-competitor-cache`. Archive validation returned
`086adf98459773e3175f4723b2b64e3f47306e42` before leadership evaluation.

The retained `null/`, `real/`, `calibration.json`, and `leadership.txt` files
are the raw calibration, accepted comparison dataset, calibration projection,
and evaluator output, respectively.
