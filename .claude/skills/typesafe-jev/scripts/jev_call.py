#!/usr/bin/env python
"""Send one System One request to Jev from the command line, or preview / fake it.

Examples
  # preview the exact JSON the SDK would send (no network, no key needed)
  uv run python .claude/skills/typesafe-jev/scripts/jev_call.py --state "Nvidia raises guidance" \
      --noul 'positive=Is this good for the stock price today?' --dry-run

  # questions from a file (JSON, same shape as the HTTP API "questions" map), state from a file
  uv run python .claude/skills/typesafe-jev/scripts/jev_call.py --state-file headlines.json \
      --questions-file questions.json

  # offline development: deterministic fake answers in the real response shape
  uv run python .claude/skills/typesafe-jev/scripts/jev_call.py --state "x" \
      --choice 'kind=What kind of news?:earnings,product,other' --mock

Inline question syntax (quote the WHOLE spec in single quotes; it contains : , and |)
  --noul   'key=instruction'
  --choice 'key=instruction:opt1,opt2,opt3'
  --score  'key=instruction:level0 desc|level1 desc|level2 desc'
Repeat any flag. Output is JSON on stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:  # noqa: BLE001
        pass


def _split_key(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        sys.exit(f"bad question spec (need key=...): {spec}")
    key, rest = spec.split("=", 1)
    return key.strip(), rest


def parse_inline(args) -> dict[str, dict]:
    qs: dict[str, dict] = {}
    for spec in args.noul or []:
        key, instr = _split_key(spec)
        qs[key] = {"type": "noul", "instructions": instr.strip('"')}
    for spec in args.choice or []:
        key, rest = _split_key(spec)
        if ":" not in rest:
            sys.exit(f"--choice needs instruction:opt1,opt2: {spec}")
        instr, opts = rest.rsplit(":", 1)
        qs[key] = {
            "type": "choice",
            "instructions": instr.strip('"'),
            "criteria": {o.strip(): None for o in opts.split(",") if o.strip()},
        }
    for spec in args.score or []:
        key, rest = _split_key(spec)
        if ":" not in rest:
            sys.exit(f"--score needs instruction:level0|level1|...: {spec}")
        instr, levels = rest.split(":", 1)
        crit = [lv.strip().strip('"') for lv in levels.split("|") if lv.strip()]
        if len(crit) < 2:
            sys.exit("--score needs at least two levels")
        qs[key] = {"type": "score", "instructions": instr.strip('"'), "criteria": crit}
    return qs


def mock_answers(state, questions: dict[str, dict]) -> dict:
    """Deterministic fake answers keyed on a hash of state+question, in the real response shape."""
    seed_base = json.dumps(state, sort_keys=True, default=str)
    answers = {}
    for key, q in questions.items():
        h = int(hashlib.sha256((seed_base + key).encode()).hexdigest(), 16)
        if q["type"] == "noul":
            answers[key] = {"type": "noul", "noul": round((h % 1000) / 1000, 3)}
        elif q["type"] == "choice":
            labels = list(q["criteria"])
            weights = [((h >> (i * 8)) % 100) + 1 for i in range(len(labels))]
            tot = sum(weights)
            probs = {lab: round(w / tot, 3) for lab, w in zip(labels, weights, strict=True)}
            best = max(probs, key=probs.get)
            answers[key] = {
                "type": "choice",
                "choice": best,
                "probabilities": probs,
                "confidence": round(probs[best], 3),
            }
        else:
            n = len(q["criteria"])
            weights = [((h >> (i * 8)) % 100) + 1 for i in range(n)]
            tot = sum(weights)
            probs = {str(i): round(w / tot, 3) for i, w in enumerate(weights)}
            score = sum(i * w / tot for i, w in enumerate(weights))
            answers[key] = {
                "type": "score",
                "score": round(score, 3),
                "probabilities": probs,
                "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                "confidence": round(max(weights) / tot, 3),
            }
    tokens = len(seed_base) // 4 + sum(len(json.dumps(q)) for q in questions.values()) // 4
    return {"model": "mock-jev", "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 0}}


def to_sdk_questions(questions: dict[str, dict]):
    from typesafe_sdk import Choice, Noul, Score

    out = {}
    for key, q in questions.items():
        if q["type"] == "noul":
            out[key] = Noul(instructions=q.get("instructions"), criteria=q.get("criteria"))
        elif q["type"] == "choice":
            out[key] = Choice(instructions=q.get("instructions"), criteria=q["criteria"])
        elif q["type"] == "score":
            out[key] = Score(instructions=q.get("instructions"), criteria=q["criteria"])
        else:
            sys.exit(f"unknown question type {q['type']!r} for {key}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", help="state as a plain string (or JSON if it parses)")
    ap.add_argument("--state-file", help="JSON file holding the state")
    ap.add_argument("--questions-file", help="JSON file: {key: {type, instructions, criteria}}")
    ap.add_argument("--noul", action="append")
    ap.add_argument("--choice", action="append")
    ap.add_argument("--score", action="append")
    ap.add_argument("--model", default=None, help="default jev-latest")
    ap.add_argument("--dry-run", action="store_true", help="print the request body and exit")
    ap.add_argument("--mock", action="store_true", help="return deterministic fake answers, no network")
    ap.add_argument("--timeout", type=float, default=None)
    args = ap.parse_args()

    if args.state_file:
        state = json.loads(Path(args.state_file).read_text())
    elif args.state is not None:
        try:
            state = json.loads(args.state)
            if not isinstance(state, (str, dict, list)):
                state = args.state
        except json.JSONDecodeError:
            state = args.state
    else:
        sys.exit("need --state or --state-file")

    questions = json.loads(Path(args.questions_file).read_text()) if args.questions_file else {}
    questions.update(parse_inline(args))
    if not questions:
        sys.exit("no questions given")

    body = {"state": state, "model": args.model or "jev-latest", "questions": questions}
    if args.dry_run:
        print(json.dumps(body, indent=2))
        return 0
    if args.mock:
        print(json.dumps(mock_answers(state, questions), indent=2))
        return 0

    _load_env()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set (put it in .env). Use --dry-run or --mock without a key.")
    from typesafe_sdk import TypeSafeAPIError, TypeSafeClient

    try:
        with TypeSafeClient(model=args.model, timeout=args.timeout) as client:
            r = client.system_one(state, to_sdk_questions(questions))
    except TypeSafeAPIError as e:
        print(f"API error {e.status} request_id={e.request_id}: {e}", file=sys.stderr)
        return 1
    out = {
        "model": r.model,
        "request_id": r.request_id,
        "answers": {k: _answer_dict(v) for k, v in r.answers.items()},
        "usage": {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _answer_dict(a) -> dict:
    if hasattr(a, "noul"):
        return {"type": "noul", "noul": a.noul}
    if hasattr(a, "choice"):
        return {"type": "choice", "choice": a.choice, "probabilities": a.probabilities, "confidence": a.confidence}
    return {
        "type": "score",
        "score": a.score,
        "probabilities": a.probabilities,
        "legend": a.legend,
        "confidence": a.confidence,
    }


if __name__ == "__main__":
    sys.exit(main())
