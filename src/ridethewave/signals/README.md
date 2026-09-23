# signals

External judgment signals that are not derived from bars: news and sentiment today, more later.

- `jev_questions.py`: the ONLY place the project's Jev questions live. Edit wording here; everything
  else imports `HEADLINE_QUESTIONS` and `headline_state()`.
- `jev_client.py`: scores headlines with Jev, concurrently, with retries and a deterministic mock;
  returns flat dicts ready for a dataframe or a database row.

Research that uses them: `scripts/study_news_jev.py` (does Jev's reading of a headline predict the
stock's forward return?). Live use waits on that study; see
`.claude/skills/typesafe-jev/references/ride-the-wave-integration.md`.
