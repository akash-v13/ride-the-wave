# Designing questions, state and thresholds for Jev

Distilled from docs.typesafe.ai (concepts/state, primitives/*, confidence, patterns/*,
model-jaggedness/jev-1.13) on 2026-09-17.

## State

State is what the questions are about. It must be text: a string, a JSON object, or an array of
text values. No images, audio or video. English is most accurate; other languages work less well.

| Shape | Use when | Example |
|---|---|---|
| string | one piece of text | `"My card was charged twice."` |
| object | several related parts (most requests) | `{"symbol": "AAPL", "headline": "...", "published": "2026-09-17T13:05Z"}` |
| array | a sequence: messages, records, headlines | `["Apple beats on revenue", "Apple guides below consensus"]` |

Rules of thumb:
- Put related information together when the decision requires comparing the parts.
- Give fields descriptive names and refer to them in the instruction by name, e.g. "Based on
  `headlines`, ...". Nested paths like `ticket.messages[0].text` are fine.
- Send only what the question needs. Large irrelevant state distracts the model and hides where an
  error came from.
- Limits (jev-1.13): 64k tokens total for state plus all questions; 32k for state plus the longest
  single question.

## Instructions and criteria

The instruction is the judgment. The criteria define the possible answers. Both accept a string or
a JSON object or array; use structure when a question has parts or when options are easily confused.

Choice options as rubrics:
```json
{"billing": {"what": "charges, invoices, refunds", "not_for": "order tracking", "examples": ["I was charged twice"]}}
```
Score levels with signals:
```json
{"summary": "One change, clearly stated", "signals": ["a single fix or feature"]}
```
Noul criteria pin the boundary: `{"true": "mentions a prior attempt to contact support", "false": "no sign of previous contact"}`.

Write level descriptions as **situations, not degrees**: "broken feature, but a workaround exists"
rather than "moderately severe". The model sees only the descriptions, not the level numbers.

## Reading the answers

- **Noul**: `noul` is P(yes). Near 1 yes, near 0 no, near 0.5 undecided. There is no separate
  confidence. If you want intensity, use a Score.
- **Choice**: `choice` is the argmax. `probabilities` sums to 1 across options. Read secondary
  options with meaningful mass (say > 0.25) when it matters. `confidence` is derived from how peaked
  the distribution is.
- **Score**: `score` is the probability-weighted mean level, e.g. 70% on level 1 and 30% on level 2
  gives 1.30. `legend` maps level numbers back to descriptions. Round to the nearest level when you
  need a discrete outcome; use the fraction only for ranking. To combine Scores with different level
  counts, divide by (levels - 1) first.
- If you want the raw JSON (fields the SDK does not model), read `raw_http_response`.

## Confidence and thresholds

"Confidence is a statistic computed from the probability distribution the answer already gives
you." It summarizes concentration, not correctness. "A confidence threshold is not one number":
gate by consequence. TypeSafe's routing example uses 0.6 as a universal floor below which the case
goes to a human, and 0.85 for autonomous high-stakes actions. Those are examples to evaluate, not
rules. Find thresholds on your own labeled data.

Three-way route:
1. High confidence or low-risk action: act.
2. Medium confidence on a consequential action: confirm or flag.
3. Below floor: escalate or reject.

Hierarchical fallback (from the classification cookbook): ask for the narrow label; if confidence is
below your bar, report the broad category the narrow label belongs to. On 60 SEC filings this took
low-confidence accuracy from 40% (forced narrow) to 70% (broad fallback) with no second call.

If all you want is the best option, take the argmax and ignore thresholds entirely.

## Patterns

**Speculative fan-out.** All questions run in parallel and "adding more questions to a call
typically doesn't add any latency". Ask primary, conditional and universal questions together and
let code pick which answers to use. Questions cannot see each other's answers. A second request is
warranted only when an answer changes what state to fetch or which options to offer.

**Composite scoring.** Score independent dimensions separately, then weight them in code. A
"disqualify on any serious violation" rule needs its own Noul, not a low weight.

**Select instead of generate.** Jev cannot generate text. To "extract" a value, find candidates in
code and ask a Choice over them; it cannot choose an option you did not include.

**Judgments as features.** Store raw answers (probabilities, not just the decision) so weights and
thresholds can change without re-running inference, and so the backtester can replay them.

## Many items (headlines, records): per item or one array state?

Two shapes work. Pick by what the questions are about.

| Shape | When | Cost / accuracy |
|---|---|---|
| **One call per item**, state = that item (plus fixed context like the symbol) | The judgment is about each item on its own: "does this headline mention earnings", "tone of this headline" | Most accurate: no irrelevant state, no indexing. 40 headlines is 40 small calls, still a few thousand tokens and well under rate limits. Use the async client to run them concurrently |
| **One call, state = array of items**, questions that refer to the set | The judgment is about the *set*: "considering all headlines, what is the net direction", "is every item a rehash" | One call, but the model must reason across items. Good for set-level questions; poor for per-item extraction, because it reads literally and large state distracts |

Do not try to get per-item answers out of an array state by writing forty indexed questions
("does `headlines[17]` mention earnings"). It works in principle, but every question drags the whole
array through the context, accuracy drops with indirection, and a per-item call is cleaner.

Aggregating in code:
- Count: sum of `noul >= threshold` over items, and separately report the number in an uncertain
  band (say 0.35 to 0.65) so the count carries its own error bar.
- Mean tone: normalize each Score to `score / (levels - 1)`, map to -1..+1 if the scale is
  symmetric, then average. Remember Scores are ordinal, not magnitude-calibrated: a mean is a
  ranking aid, not a measurement.
- Store every per-item answer; recompute aggregates later without re-inference.

## Known limitations of jev-1.13 and the workaround for each

| Limitation | Workaround |
|---|---|
| Answers the question you wrote, not the one you meant | State exact conditions and boundary cases |
| Cannot count items, characters or occurrences | Count in code; ask per item |
| Weak on hex, RGB, numeric comparison | Convert to words or computed buckets in code |
| Score is not numerically calibrated for magnitude | Use scores for threshold checks and ranking, not interpolation |
| Treats dates as text | Extract components as Choices; compare in code |
| Double negatives and multi-hop reasoning degrade accuracy | Ask directly; name the relevant state field |
| Large irrelevant state distracts | Filter state in code |
| Follows instructions embedded in the data | Explicit criteria; test with adversarial inputs |
| Contradictory instructions vs criteria confuse it | Align wording |
| No structural invariants (P(x) + P(not x) may not equal 1 across questions) | Do not transfer thresholds between questions |
| Not trained for generation | Choice over bounded options, or a generative model |
