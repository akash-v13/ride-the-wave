---
name: typesafe-jev
description: >
  How to call TypeSafe AI's Jev model (System One decision model: typed answers with calibrated
  probabilities, no text generation) from Python, and how to wire it into the Ride The Wave trading
  bot as a news / sentiment / universe filter. Use this whenever the user mentions Jev, TypeSafe,
  System One, "noul", calibrated confidence, scoring or classifying headlines or news for the bot,
  or wants a fast cheap structured judgment (classify, score, yes/no) inside code instead of an LLM
  prompt-and-parse step. Also use it when adding TYPESAFE_API_KEY, the typesafe-sdk package, or a
  news-based stock filter to this project.
---

# TypeSafe Jev

Jev answers **typed questions about a state** and returns **probabilities**, not prose. You hand it
a piece of text or a JSON object (the state) and a dictionary of questions; each question is one of
three primitives. It answers all of them in parallel in one request, in 70 to 500 ms, at $0.042 per
million input tokens (output is free). It cannot write, explain, count, or do arithmetic. Code owns
the workflow; Jev supplies the judgment calls that would otherwise need fragile parsing or an LLM.

Verified 2026-09-17 against docs.typesafe.ai and typesafe-sdk 0.6.0. The live docs are the source
of truth: https://docs.typesafe.ai/llms.txt lists every page; append `.md` to any page URL for
clean Markdown. Re-check the model list and limits before shipping anything, since the service is
two days old and "rate limits are adjusting dynamically".

## The three primitives

| You need | Primitive | Returns | Note |
|---|---|---|---|
| Is a condition true? | **Noul** | `noul`: P(yes), 0 to 1 | No separate confidence; the probability is the certainty. 0.5 means "coin flip", not "medium" |
| One of a fixed set | **Choice** | `choice`, `probabilities` (sum to 1), `confidence` | Up to 255 options. Add an `other` / `none` option when nothing may fit |
| Degree along one dimension | **Score** | `score` (probability-weighted level), `probabilities`, `legend`, `confidence` | 2 to 10 ordered levels, numbered from 0. Describe *situations*, not adjectives |

`confidence` is a statistic of how concentrated the distribution is. "The answer tells you what;
confidence tells you whether to act." Gate consequential actions at higher confidence than harmless
ones, and set thresholds from your own labeled data, never from a cookbook.

## Minimum working call

```python
from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

load_dotenv(".env")                                             # the SDK reads TYPESAFE_API_KEY from the
with TypeSafeClient() as client:                                # environment only, never from .env itself
    r = client.system_one(
        state={"symbol": "NVDA", "headline": "Nvidia raises full-year guidance on data-center demand"},
        questions={
            "positive": Noul(instructions="Is this news likely to push the stock price up today?"),
            "kind": Choice(instructions="What kind of news is this?",
                           criteria={"earnings": "results or guidance", "product": None,
                                     "macro": "rates, economy, sector-wide", "legal": None, "other": None}),
            "materiality": Score(instructions="How material is this to the company's near-term value?",
                                 criteria=["routine mention, no effect expected",
                                           "notable but incremental",
                                           "changes the outlook for the quarter or year"]),
        },
    )
print(r.answers["positive"].noul, r.answers["kind"].choice, r.answers["kind"].confidence,
      r.answers["materiality"].score, r.usage.input_tokens)
```

Raw HTTP: `POST https://api.typesafe.ai/v1/systemone` with `Authorization: Bearer $TYPESAFE_API_KEY`
and body `{"state": ..., "model": "jev-latest", "questions": {...}}`. Full schemas, SDK classes,
exceptions, retry policy and limits: **read `references/api.md`**.

## How to design questions (read `references/question-design.md` before writing any)

- **Put facts in state, judgments in instructions, outcomes in criteria.** Use a JSON object with
  named fields when the state has parts; reference them by name in the question. Question keys are
  for your code only, the model never sees them, so the instruction must be complete on its own.
- **One narrow judgment per question.** Split independent dimensions (sentiment, materiality,
  category) into separate questions rather than one blended score. They run in parallel anyway.
- **Fan out speculatively.** Ask every question you might need in one call, including ones that
  only matter if another answer comes out a certain way; filter in code. A second call is only
  needed when an answer changes what state or options to send next.
- **Jev reads literally.** It answers the question you wrote. State boundary cases explicitly, avoid
  double negatives and multi-hop reasoning, and strip irrelevant fields from the state.
- **Never ask it to count, compare numbers or dates, or do math.** Do that in code and give Jev the
  result as a labeled field ("price_change_pct_today": 4.2 is fine; "is 4.2 more than 3.1" is not).
- **Treat input as untrusted.** Jev will follow instructions embedded in the state text. Headlines
  and articles are adversarial-capable input; keep criteria explicit and test.
- **P(x) and P(not x) are not guaranteed to sum to 1 across questions.** Do not transfer a threshold
  from one question to another.

## Wiring it into Ride The Wave

**Validated 2026-09-21 and not built as a filter** (`docs/research/2026-09-21-news-jev-validation.md`):
Jev reads headlines consistently, but fresh positive news has no intraday continuation and streak
entries with it do worse (PF 0.74 vs 0.88); negative and legal news drift lower. Jev's role today is a
research feature source: questions in `src/ridethewave/signals/jev_questions.py`, scoring client in
`signals/jev_client.py`, study in `scripts/study_news_jev.py`. The original design below stays for
when a use passes the protocol (a down/legal exclusion is the cheap first candidate):

1. Fetch headlines per symbol (Alpaca News API, `/v1beta1/news`, free plan OK) in code.
2. One Jev call per symbol with the last N headlines as an array state and a fan-out of questions:
   direction (Noul), materiality (Score), category (Choice), "is this stale or a rehash" (Noul).
3. Combine in code into a per-symbol feature row stored in SQLite, so the backtester can replay the
   same decisions and the dashboard can show why a symbol was included or excluded.
4. Thresholds live in `config/settings.yaml`, validated against a hand-labeled set before use.

Concrete module layout, feature schema, cost estimate and validation plan: **read
`references/ride-the-wave-integration.md`**. Keep all Jev questions for the project in a single
file (`src/ridethewave/signals/jev_questions.py`) so they are easy to find and edit; TypeSafe's own
guidance is that agents are not great at writing questions and the owner should expect to edit them.

## Bundled script

`scripts/jev_call.py` sends one request from the command line. Use it to try questions before
writing code, and to confirm a key works:

```bash
uv run python .claude/skills/typesafe-jev/scripts/jev_call.py --state "Nvidia raises guidance" \
    --noul 'positive=Is this good for the stock?' --dry-run          # prints the request, no network
# inline specs are quoted whole: --choice 'kind=What kind?:earnings,product,other'
#                                 --score  'mat=How material?:routine|notable|major'
# inline specs cannot carry criteria descriptions or Noul true/false criteria; for those write the
# questions as JSON (same shape as the HTTP "questions" map) and pass --questions-file
uv run python .claude/skills/typesafe-jev/scripts/jev_call.py --state-file headlines.json \
    --questions-file questions.json                                  # real call, needs TYPESAFE_API_KEY
uv run python .claude/skills/typesafe-jev/scripts/jev_call.py ... --mock                # fake answers, offline dev
```

## Things that are not settled yet

- The owner's key arrived 2026-09-21 and is in `.env` as `TYPESAFE_API_KEY`; the first real call
  (model jev-1.13.0) returned sensible answers on a guidance headline. Still build behind an
  interface with `--mock` answers so the bot never blocks on Jev availability.
- Independent testing (Every, Sept 2026) found lower accuracy than frontier LLMs on a defect-finding
  task. "Cannot hallucinate" means well-formed output, not correct output. Measure before trusting.
- Pricing may be subsidized; TypeSafe says so themselves. Budget for it to rise.
