# Eval runs

Recorded baselines from `scripts/eval.py`, kept so a change can be argued about with numbers
instead of impressions.

Every run here is bound to the corpus and the chunk ids it was taken against. Re-ingestion
replaces chunks with fresh UUIDs, so a run from before one cannot be compared with a run from
after it — the dataset has to be re-authored first, and the old numbers become history rather
than a baseline.

| file | what it is |
|---|---|
| `baseline.json` | **The baseline.** 33 cases against the staging corpus, `golden.json` with any-of matching. Compare against this. |
| `baseline-strict-allof.json` | The same run before `match: any` existed. Recall is understated — a correct answer citing an equally valid passage scored 0.00. Kept because it is the run that exposed the flaw. |

## The baseline, and what it says

```
recall_at_k 0.88   mrr 0.793   grounded_rate 0.844   p50 13.2s   p95 22.0s
single_hop 1.0   exact_identifier 1.0   follow_up 1.0   multi_hop 0.40
```

Zero errors across 33 cases, and `citation_concentration` at 0.10 — the floor to watch when
the learned relevance prior is switched on, since concentration rising while recall holds is
the signature of entrenchment.

**`exact_identifier` at 1.0 is the RRF-ordering fix.** Bare-identifier queries are the entire
justification for the lexical arm, and before that fix a lexical-only hit could not reach the
rerank pool at all whenever the dense arm filled it.

**`multi_hop` at 0.40 is the weak point, and the trace says why.** All five multi-hop cases
exited `sufficient` at `hops=1` — the loop never took a second hop on any of them. The
sufficiency grader is calling one retrieval good enough for questions that need two passages,
so the answer is written from half the picture. `grounded_rate` stays high on exactly those
cases because the model faithfully grounds the half it was given, which is why answer quality
alone would never have surfaced this.

That is a hypothesis about one component, and it is worth testing before anything else in the
pipeline is tuned: raising the hop budget cannot help if the loop is choosing not to spend it.

## Two things the numbers do not say on their own

`answered_when_it_should_not_have: 2` in these runs predates the refusal/invention split. Both
cases had in fact refused, in prose, because the question was topically adjacent to real
content — retrieval returned passages, the loop exited `max_hops`, and the model said the
context did not cover it. Later runs separate that from a genuine invention; see
`refused_without_falling_back`.

`p50` above 13s is dominated by the cases that spend two hops. Nine of 33 exited `max_hops`,
each paying a full extra retrieval, rerank and grade cycle before answering anyway.

## On adding alternates after a run

`single-backend-hosting` scored 0.00 for three runs while answering the question correctly
and citing two passages that answer it as completely as the ones the dataset named — the
repo's file map (`api/ ← the entire backend`) and the architecture summary (`/api/generate` —
the *only* server code we own). Those were added as alternates.

This is the kind of edit that can quietly become p-hacking, so the rule is: **add an
alternate only after reading the passage and finding that it genuinely answers the
question.** Not because it was retrieved, not because it moves a number. A passage that is
merely topical is a miss and should stay a miss.

`multi-ai-stack` scored 0.00 in the same runs and was left alone: it cited the pitch and a
flow diagram, neither of which names the model or the gateway. That one is a real retrieval
failure and the number should say so.
