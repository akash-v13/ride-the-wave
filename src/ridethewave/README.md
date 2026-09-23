# src/ridethewave

The Python package. Import as `ridethewave`.

| Module | Responsibility | Network? | DB? |
|---|---|---|---|
| `config.py` | Load and validate settings + secrets | no | no |
| `clients.py` | Build the Alpaca SDK clients (paper only) | no | no |
| `models.py` | Plain dataclasses shared by every layer | no | no |
| `engine.py` | Glue: bar/tick in, strategy, signals to order manager | no | writes positions |
| `runner.py` | The live loop: wait for open, poll, tick, shutdown + ledger | via others | via others |
| `data/` | Universe, snapshot polling, bar aggregation, historical bars | yes | writes bars |
| `strategy/` | Entry and exit decisions | **no** | **no** |
| `execution/` | Broker interface, Alpaca broker, order manager, position book | yes | orders/trades |
| `portfolio/` | Position sizing, daily ledger, reinvestment | no | no |
| `backtest/` | Simulated broker, replay engine, report | historical bars only | backtest tables |
| `storage/` | SQLite schema and repositories | no | yes |
| `operator/` | Kill switches, check-in reports, alerts, notifications | no | reads; writes `risk` state |
| `signals/` | External judgment signals: the project's Jev questions and a concurrent scoring client | yes (TypeSafe) | no |
| `ui/` | Streamlit dashboard | no | read only |

The "no network / no DB" rule for `strategy/` is what keeps backtests honest. See docs/architecture.md section 4.3.
