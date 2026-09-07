# Eval runs

Recorded baselines from `scripts/eval.py`, kept so a change can be argued about with
numbers instead of impressions.

Every run here is bound to the corpus and the chunk ids it was taken against. Re-ingestion
replaces chunks with fresh UUIDs, so a run from before one cannot be compared with a run
from after it — the dataset has to be re-authored first, and the old numbers become history
rather than a baseline.

| file | dataset | what it is |
|---|---|---|
| `baseline-strict-allof.json` | golden.json, before `match: any` | First full measurement of the system. Recall is understated: every question was scored all-of, so a correct answer citing an equally valid passage scored 0.00. Kept because it is the run that exposed the flaw. |
