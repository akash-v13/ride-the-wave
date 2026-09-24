# docs/books

Reference texts the owner supplied (2026-09-17). PDFs are gitignored; only this index is tracked.

| File | Book | Relevance to this project |
|---|---|---|
| `analysis-of-financial-time-series-*.pdf` | Tsay, *Analysis of Financial Time Series*, 2nd ed., Wiley 2005 | Volatility (GARCH) modelling and high-frequency chapters: better noise estimates for exits, intraday seasonality, regime detection |
| `machine-learning-in-finance-*.pdf` | Dixon, Halperin, Bilokon, *Machine Learning in Finance: From Theory to Practice*, Springer 2020 | Supervised-learning chapters: the planned classifier on the feature dataset; walk-forward validation |
| `ssrn-3247865.pdf` | Kakushadze, Serur, *151 Trading Strategies*, SSRN 3247865 (2018; also Palgrave Macmillan) | A catalogue across every asset class; mapped against our Alpaca provisions in `docs/research/2026-09-23-kakushadze-151-feasibility.md`. Stock chapter (3) and ETF chapter (4) are the usable parts; Appendix A's open-to-close alphas became feature 19 |
| `RLforFinaanceRao.pdf` | Rao, Jelvis, *Foundations of Reinforcement Learning with Applications in Finance*, CRC 2022 (Stanford CME 241 text) | Optimal execution and order-book chapters later; RL for trading not until far more data exists |

Skills distilled from these go in `.claude/skills/`; experiments that apply them go in `docs/research/`.

Status: Dixon → `.claude/skills/dixon-ml-finance/` (2026-09-17). Kakushadze → feasibility map and feature 19 (2026-09-23). Tsay and Rao not yet distilled.
