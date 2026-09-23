# .claude/skills

Project-local skills for Claude Code. Each folder is one skill: a `SKILL.md` with instructions,
`references/` for detail loaded on demand, `scripts/` for runnable helpers, `evals/` for test prompts.

- `typesafe-jev/`: how to call TypeSafe AI's Jev decision model and wire it into this bot as a
  news / sentiment filter. Written 2026-09-17 from the TypeSafe docs and typesafe-sdk 0.6.0.
- `dixon-ml-finance/`: modelling and validation rules distilled from Dixon, Halperin & Bilokon,
  *Machine Learning in Finance* (2020), with page references, chapter notes, a phase-13 plan and
  `scripts/evalkit.py` (walk-forward folds, calibration, χ², posterior win rate, Bayes factor,
  Diebold-Mariano). Written 2026-09-17.
