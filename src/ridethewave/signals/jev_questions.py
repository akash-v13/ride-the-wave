"""The project's Jev questions about a single headline for a single symbol. Edit wording here only.

Design rules (skill: typesafe-jev): facts in state, judgments in instructions, outcomes in criteria;
one narrow judgment per question; no counting or arithmetic asked of the model; explicit boundaries.
"""

from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score

QUESTIONS_VERSION = "2026-09-21.1"


def headline_state(symbol: str, headline: str, summary: str | None, source: str | None, symbols: list[str]) -> dict:
    """What the model sees. `symbol` is the one we are judging for; `tagged_symbols` shows the rest."""
    state = {"symbol": symbol, "headline": headline.strip()}
    if summary:
        state["summary"] = summary.strip()[:600]
    if source:
        state["source"] = source
    others = [s for s in symbols if s != symbol][:8]
    if others:
        state["other_tagged_symbols"] = others
    return state


HEADLINE_QUESTIONS = {
    "direction": Choice(
        instructions=(
            "Judging only the company in `symbol`, what is the likely effect of this news on its share price "
            "over the next few hours after publication?"
        ),
        criteria={
            "up": "clearly positive for the company's value or prospects",
            "down": "clearly negative for the company's value or prospects",
            "mixed": "positive and negative elements of similar weight",
            "none": "no price-relevant information about this company",
        },
    ),
    "positive": Noul(
        instructions="Is this news likely to push the share price of the company in `symbol` up on the day?",
        criteria={
            "true": "new, company-specific information that investors would treat as good: beats, raised guidance, "
            "large contracts, buybacks, approvals, upgrades",
            "false": "bad news, no news, generic market commentary, lists, opinion, "
            "or news mainly about other companies",
        },
    ),
    "materiality": Score(
        instructions="How material is this news to the near-term value of the company in `symbol`?",
        criteria=[
            "routine mention: listicle, analyst chatter, minor product note, company named in passing",
            "notable but incremental: partnership, mid-size contract, moderate guidance change, rating change",
            "major: earnings surprise, large guidance change, merger or acquisition, regulatory action, recall",
        ],
    ),
    "kind": Choice(
        instructions="What kind of news is this for the company in `symbol`?",
        criteria={
            "earnings_or_guidance": "results, outlook, guidance",
            "product": "launches, contracts, partnerships, recalls",
            "capital_action": "buyback, dividend, share offering, debt, dilution",
            "legal_regulatory": "lawsuits, investigations, regulators, antitrust",
            "macro_or_sector": "economy, rates, sector-wide moves, market commentary",
            "analyst_or_opinion": "ratings, price targets, columns, podcasts",
            "list_or_roundup": "'stocks to watch', movers lists, whale-activity roundups",
            "other": None,
        },
    ),
    "stale": Noul(
        instructions=(
            "Is this item a generic list, roundup, opinion piece, or a rehash of already-known information, rather "
            "than new company-specific news about the company in `symbol`?"
        ),
    ),
    "toxic": Noul(
        instructions=(
            "Does this news mention fraud, an accounting restatement, delisting, bankruptcy, going-concern doubt, or "
            "a dilutive share offering involving the company in `symbol`?"
        ),
    ),
}
