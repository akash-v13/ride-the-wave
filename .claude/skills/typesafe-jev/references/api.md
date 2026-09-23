# Jev API and Python SDK reference

Verified 2026-09-17 against docs.typesafe.ai/api.md, /models.md, /sdk/python/* and by introspecting
the installed `typesafe-sdk` 0.6.0. Re-verify against the live docs when the SDK version changes:
outdated references make agents invent fields.

## HTTP API

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <TYPESAFE_API_KEY>
Content-Type: application/json
```
Keys: https://console.typesafe.ai/settings/keys. Playground: https://console.typesafe.ai/playground.

Request:
```json
{
  "state": "string | object | array of text values",
  "model": "jev-latest",
  "questions": {
    "q_noul":   {"type": "noul",   "instructions": "Is ...?", "criteria": {"true": "...", "false": "..."}},
    "q_choice": {"type": "choice", "instructions": "Which ...?", "criteria": {"a": "desc or null", "b": null}},
    "q_score":  {"type": "score",  "instructions": "How ...?", "criteria": ["level 0 desc", "level 1 desc", "level 2 desc"]}
  }
}
```
- `instructions` may be a string, object or array (or null). `criteria` values may be strings,
  objects or arrays.
- Noul `criteria` is optional. Choice `criteria` is required (1 to 255 options). Score `criteria` is
  required, 2 to 10 ordered levels, level numbers start at 0.
- Question keys are for your code; the model does not see them.

Response:
```json
{
  "model": "jev-1.13.0",
  "answers": {
    "q_noul":   {"type": "noul",   "noul": 0.93},
    "q_choice": {"type": "choice", "choice": "a", "probabilities": {"a": 0.81, "b": 0.19}, "confidence": 0.74},
    "q_score":  {"type": "score",  "score": 1.30, "probabilities": {"0": 0.0, "1": 0.7, "2": 0.3},
                 "legend": {"0": "level 0 desc", "1": "level 1 desc", "2": "level 2 desc"}, "confidence": 0.58}
  },
  "usage": {"input_tokens": 412, "output_tokens": 0}
}
```
Response header `x-typesafe-request-id` identifies the call for support.

Errors:

| Status | Meaning | Do |
|---|---|---|
| 401 | Missing or invalid API key | Check `Authorization: Bearer` |
| 422 | Body failed validation; details name the field | Fix the question shape |
| 429 | Rate limited | Back off; honor `retry-after` / `retry-after-ms` |
| 529 | Overloaded | Retry after a delay |

## Models and limits (jev-1.13)

| Alias | Points to |
|---|---|
| `jev-latest` | `jev-1.13.0` (stable, default) |
| `jev-preview` | `jev-1.13.0` (newest, official or not) |

- Price: $0.042 per million input tokens; output free.
- Context: 64k tokens for state plus all questions; 32k for state plus the longest single question.
- Rate limits: 250,000 tokens/second, 1,200 requests/minute, "adjusting dynamically".
- Input: text only. English best.
- `GET /v1/models` lists models (SDK: `client.models.list()`).

## Python SDK (`typesafe-sdk` 0.6.0, Python >= 3.10)

Install into this project: `uv sync --group jev` (already declared in pyproject `dependency-groups.jev`).

Environment variables: `TYPESAFE_API_KEY` (required), `TYPESAFE_BASE_URL` (default
`https://api.typesafe.ai`), `TYPESAFE_DEFAULT_MODEL` (default `jev-latest`), `TYPESAFE_LOG_LEVEL`.
Default HTTP timeout 10 s. The SDK does **not** read `.env`; load it yourself
(`from dotenv import load_dotenv; load_dotenv(".env")`) before constructing the client.

Top-level exports: `TypeSafeClient`, `AsyncTypeSafeClient`, `Noul`, `Choice`, `Score`, `RetryPolicy`,
`SystemOneResponse`, `NoulAnswer`, `ChoiceAnswer`, `ScoreAnswer`, `Usage`, the exception classes,
`constants`.

Client (all keyword-only):
```python
TypeSafeClient(api_key=None, model=None, retry=None, timeout=None, headers=None,
               transport=None, http_client=None, base_url=None)
```
Use as a context manager (`with TypeSafeClient() as client:`) or call `client.close()`.

Call:
```python
client.system_one(state, questions, *, model=None, retry=None, timeout=None,
                  extra_headers=None, extra_body=None) -> SystemOneResponse
```
`state`: `str | Mapping | Sequence` of JSON values. `questions`: mapping of key to `Noul | Choice | Score`
(or raw dicts for unreleased fields). `extra_body` passes unmodeled request fields.

Questions (msgspec structs, keyword args):
```python
Noul(instructions=None, criteria=None)          # criteria: {"true": ..., "false": ...}
Choice(criteria={...}, instructions=None)       # criteria: {label: description | None}
Score(criteria=[...], instructions=None)        # criteria: ordered list, one per level from 0
```

Response:
```python
r.model            # "jev-1.13.0"
r.usage            # Usage(input_tokens, output_tokens)
r.answers          # dict[str, NoulAnswer | ChoiceAnswer | ScoreAnswer]
r.nouls, r.choices, r.scores   # dicts filtered by type
r.request_id       # from x-typesafe-request-id
r.raw_http_response
NoulAnswer.noul                                   # float 0..1
ChoiceAnswer.choice, .probabilities, .confidence  # str, dict[str,float], float
ScoreAnswer.score, .probabilities, .legend, .confidence   # float, dict[int,float], dict[int,...], float
```

Async: `async with AsyncTypeSafeClient() as client: r = await client.system_one(...)`. Same
signature. Use it to fan many symbols out concurrently.

Retries (automatic by default):
```python
RetryPolicy(max_retries=2, backoff_initial=0.5, backoff_max=5.0, backoff_jitter=0.25,
            http_statuses={408, 429, 500..599}, respect_retry_after=True,
            api_connection_error=True, api_timeout_error=True, exceptions=set(), predicate=None,
            timeout=30.0)   # total retry budget per call; None removes it
```
Pass `retry=` on the client or per call. `max_retries=0` disables.

Exceptions:
```
TypeSafeError
├── TypeSafeAPIError            .status .body .headers .endpoint .request_id
│   ├── TypeSafeBadRequestError (400)
│   ├── TypeSafeAuthenticationError (401)
│   ├── TypeSafePermissionDeniedError (403)
│   ├── TypeSafeNotFoundError (404)
│   ├── TypeSafeUnprocessableEntityError (422)
│   ├── TypeSafeRateLimitError (429)   .retry_after_ms
│   ├── TypeSafeInternalServerError (5xx)
│   └── TypeSafeAPIResponseValidationError   .field_path
└── TypeSafeAPIConnectionError
    └── TypeSafeAPITimeoutError   .timeout
```
Catch `TypeSafeAPIError` for anything with an HTTP response; log `request_id`.

## Official skill and cookbooks

TypeSafe publishes its own Claude Code skill (`claude plugin marketplace add typesafe-ai/skills`,
then `claude plugin install typesafe@typesafe-ai`). It points at the live docs rather than
embedding them. This project skill is the local, project-specific complement: it records what was
verified on 2026-09-17 and how Jev fits Ride The Wave. If the two disagree, the live docs win.

Cookbooks worth reading for this project (append `.md` to fetch as Markdown):
- https://docs.typesafe.ai/cookbooks/classification_using_confidence (hierarchical fallback)
- https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook (route uncertain Nouls to review)
- https://docs.typesafe.ai/cookbooks/parallel_questions (13 questions in one call)
- https://docs.typesafe.ai/cookbooks/classifying_rag_passages (relevance filtering)
- https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery (judgments as ML features)
