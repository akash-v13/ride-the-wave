# Using Jev inside Ride The Wave

**Validation result (2026-09-21, `docs/research/2026-09-21-news-jev-validation.md`):** Jev reads headlines consistently, but positive news has no intraday forward edge and is a mild negative for the streak strategy's entries; negative and legal news drift lower. The entry-confirmer design below was NOT built. Jev's current role is a research feature source (`src/ridethewave/signals/`), with a possible down/legal exclusion as low-priority risk hygiene. The rest of this page is the original design, kept for when a use passes the protocol.


Written 2026-09-17, before the owner had API access. Everything here is a design to build behind
an interface; the bot must run unchanged when Jev is unavailable.

## Where it fits

The v1 strategy trades on minute bars alone. The owner's roadmap adds news and sentiment to pick
better stocks. Jev is a good fit for the *judgment* part of that: given a symbol's recent headlines,
is the news positive, how material is it, what kind is it, is it fresh. It is not a fit for the
strategy arithmetic, for anything needing an explanation, or for counting or comparing numbers.

Three insertion points, in order of value and safety:

1. **Universe filter (safest).** After the most-actives screen, drop symbols whose recent news is
   clearly negative or legally toxic (delisting, fraud, dilution). Wrong answers cost an
   opportunity, never money.
2. **Entry confirmer.** When the streak rule fires, require the symbol's news feature to be at least
   neutral. Wrong answers block trades; still no direct loss.
3. **Sizing modifier (last, needs evidence).** Scale position size by materiality and direction.
   This is the only one where a wrong answer costs money; do it only after the backtester shows
   the feature has edge.

## Data source

Alpaca News API: `GET https://data.alpaca.markets/v1beta1/news?symbols=AAPL,TSLA&limit=50&start=...`
with the same auth headers as market data. Free plan includes it (Benzinga feed). alpaca-py:
`NewsClient(api_key, secret_key).get_news(NewsRequest(symbols=..., start=..., limit=...))`.
Verify the request class names against the installed SDK before use. Fields: `headline`,
`summary`, `created_at`, `symbols`, `source`, `url`.

## Proposed module layout

```
src/ridethewave/signals/
  README.md
  jev_questions.py     the ONLY place questions live; owner edits here
  jev_client.py        thin wrapper: build state, call SDK (or mock), map answers to NewsFeature
  news.py              fetch + dedupe headlines per symbol from Alpaca, cache in SQLite
  features.py          NewsFeature dataclass + combine rule + thresholds from settings
```

Interface the rest of the bot sees:
```python
class NewsSignal(Protocol):
    def features_for(self, symbols: list[str], as_of: datetime) -> dict[str, NewsFeature]: ...
```
Implementations: `JevNewsSignal` (real), `MockNewsSignal` (deterministic fake answers for tests and
for running without a key), `NullNewsSignal` (returns "no news, neutral" for everything; the
default until the owner turns the feature on in settings).

## Questions (starting point; expect the owner to edit)

State per symbol, one call:
```json
{"symbol": "NVDA",
 "headlines": [{"age_minutes": 12, "source": "benzinga", "text": "Nvidia raises full-year guidance"},
               {"age_minutes": 190, "source": "benzinga", "text": "Nvidia supplier reports delays"}],
 "price_change_pct_today": 3.4}
```
`age_minutes` and `price_change_pct_today` are computed in code and given as labeled numbers;
never ask Jev to compare dates or prices.

```python
QUESTIONS = {
    "direction": Choice(
        instructions="Considering the `headlines` together, what is the likely effect on the stock price over the next few hours?",
        criteria={"up": "clearly positive for the company's value", "down": "clearly negative",
                  "mixed": "positive and negative items of similar weight", "none": "no price-relevant news"}),
    "materiality": Score(
        instructions="How material is the most important headline to the company's near-term value?",
        criteria=["routine mention: analyst note, listicle, minor product update",
                  "notable: partnership, contract, moderate guidance change",
                  "major: earnings surprise, large guidance change, M&A, regulatory action"]),
    "kind": Choice(instructions="What kind is the most important headline?",
        criteria={"earnings": None, "guidance": None, "product": None, "macro": "economy, rates, sector-wide",
                  "legal_regulatory": None, "capital_action": "offering, dilution, buyback, dividend",
                  "hype": "meme, social media, listicle", "other": None}),
    "toxic": Noul(instructions="Do the `headlines` mention fraud, delisting, bankruptcy, going-concern doubt, or a dilutive share offering?"),
    "stale": Noul(instructions="Is every headline a repeat or rehash of news that would already be reflected in the price? Use `age_minutes` as given."),
}
```

## Feature row (store raw answers, decide later)

```python
@dataclass
class NewsFeature:
    symbol: str; as_of: datetime; n_headlines: int
    direction: str; p_up: float; p_down: float; direction_conf: float
    materiality: float; materiality_conf: float
    kind: str; p_toxic: float; p_stale: float
    model: str; input_tokens: int
```
Table `news_features (symbol, as_of, ..., raw_json)` in SQLite. The backtester loads rows by
`as_of <= bar time` so it never sees the future.

## Combine rule (in code, thresholds in settings.yaml)

```yaml
news:
  enabled: false
  provider: null            # null | mock | jev
  max_headline_age_minutes: 360
  exclude_if_p_toxic_above: 0.5
  require_direction_not: [down]
  min_direction_confidence: 0.6      # below this, treat as "none"
  min_materiality_for_boost: 1.5     # only used by the sizing modifier
```
Below `min_direction_confidence` fall back to "none" (hierarchical fallback), do not force a call.

## Cost and rate

65 symbols, 10 headlines each, roughly 600 tokens of state plus 400 of questions per call: about
65k tokens per refresh. Refreshing every 15 minutes over a 6.5 hour day is 26 refreshes, roughly
1.7M tokens, about $0.07 per day at list price. Rate limits (1,200 requests per minute) are not a
concern at this scale. Latency of 70 to 500 ms per call means a full refresh takes well under a
minute sequentially; use the async client if it ever matters.

## Validation before it touches a trade

1. Collect 300 headlines across the universe; the owner labels direction and materiality by hand
   (a spreadsheet is fine).
2. Run the questions; report accuracy per question, calibration (does p_up of 0.8 mean right 80%
   of the time?), and confusion between `mixed` and `none`.
3. Iterate on wording, not thresholds, until accuracy is acceptable. Then pick thresholds.
4. Backtest with and without the filter on the same dates and universe; compare profit factor,
   trade count and hit rate. Report both feeds.
5. Only then set `news.enabled: true` for the universe filter, and run paper for a week before
   considering the entry confirmer.
