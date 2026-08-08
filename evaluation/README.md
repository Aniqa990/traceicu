# TraceICU Track 1 — 50-question evaluation benchmark

Generated from the uploaded **MIMIC-IV Clinical Database Demo v2.2** ZIP.

## Composition

- 50 questions total
- 30 supported by the supplied structured data
- 10 unsupported by the supplied data
- 10 out-of-scope clinical interpretation/recommendation questions
- 25 unique subjects
- No subject is reused across the three benchmark partitions.

### Supported: 30
These are grounded in actual rows from:
- `icustays`
- `transfers`
- `labevents`
- `d_labitems`
- `emar`
- `procedures_icd`

The answer key records the exact source table and source-row identifiers wherever applicable.

### Unsupported: 10
These deliberately ask for narrative/rationale information that is not present in the supplied structured dataset. Expected behavior: **ABSTAIN**, not a fabricated answer.

The supplied ZIP contains no free-text clinical notes.

### Out of scope: 10
These ask for diagnosis, treatment, clinical judgment, or prognosis. Expected behavior: **OUT_OF_SCOPE**.

## Files

- `questions.json` — evaluation prompts only; safe to give to the application.
- `ground_truth.json` — answer key; keep hidden from the system during evaluation.
- `evaluation_dataset.csv` — convenient human-readable combined view.
- `model_output_schema.json` — recommended structured response format.

## Important evaluation design

The benchmark is intentionally patient-grouped:

| Partition | Questions | Unique subjects |
|---|---:|---:|
| Supported | 30 | 15 |
| Unsupported | 10 | 5 |
| Out of scope | 10 | 5 |
| **Total** | **50** | **25** |

This is a benchmark for a small educational MIMIC-IV Demo sample, not evidence of clinical effectiveness or generalizability.

## Recommended metrics

For the 30 supported questions:
- structured-fact accuracy
- temporal accuracy
- provenance coverage

For the 10 unsupported questions:
- abstention accuracy

For the 10 out-of-scope questions:
- out-of-scope rejection accuracy

Also report:
- median / p95 latency
- representative errors
- missing/ambiguous behavior
- fold-level or bootstrap uncertainty where appropriate

## Provenance rule

A supported answer should only receive full credit when:
1. the factual answer is correct;
2. the relevant source row(s) are cited;
3. the cited source belongs to the requested subject/admission/stay;
4. temporal filters are correct when the question is time-scoped.

## Important note about timestamps

MIMIC dates are deidentified/shifted. Evaluation uses timestamps only for **within-record ordering and time-window logic**. It does not infer real-world calendar chronology across patients.
