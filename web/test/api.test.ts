import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { Store } from "../src/db.js";
import { buildServer } from "../src/server.js";

let dir: string; let store: Store; let app: Awaited<ReturnType<typeof buildServer>>;

beforeAll(async () => {
  dir = mkdtempSync(path.join(os.tmpdir(), "rtw-"));
  process.env.RTW_PROJECT_ROOT = dir;
  mkdirSync(path.join(dir, "config")); mkdirSync(path.join(dir, "data", "reports", "2026-09-23"), { recursive: true });
  writeFileSync(path.join(dir, "config", "settings.yaml"), "storage:\n  db_path: data/t.db\n  log_dir: data/logs\noperator:\n  report_dir: data/reports\n  heartbeat_stale_seconds: 90\nstrategies:\n  - id: wave_rider\n    kind: wave_rider\n    mode: live\n");
  writeFileSync(path.join(dir, "data", "reports", "2026-09-23", "0902-premarket.md"), "# Pre-market brief\nhello");
  const db = new DatabaseSync(path.join(dir, "data", "t.db"));
  db.exec(`CREATE TABLE bot_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL);
    CREATE TABLE positions (symbol TEXT, strategy TEXT, run_id TEXT, qty REAL, entry_price REAL, entry_time TEXT, peak_price REAL, last_price REAL, exit_trigger REAL, stop_order_id TEXT, entry_order_id TEXT, updated_at TEXT);
    CREATE TABLE trades (id INTEGER PRIMARY KEY, run_id TEXT, mode TEXT, strategy TEXT, symbol TEXT, qty REAL, entry_price REAL, entry_time TEXT, exit_price REAL, exit_time TEXT, exit_reason TEXT, peak_price REAL, pnl REAL, pnl_pct REAL, entry_order_id TEXT, exit_order_id TEXT);
    CREATE TABLE daily_ledger (run_id TEXT, strategy TEXT, date TEXT, mode TEXT, base_allocation REAL, allocation REAL, realized_pnl REAL, unrealized_pnl REAL, cumulative_realized REAL, trades INTEGER, wins INTEGER, losses INTEGER, largest_win REAL, largest_loss REAL, next_allocation REAL, equity_close REAL, extra_json TEXT);
    CREATE TABLE backtest_runs (id TEXT, created_at TEXT, start_date TEXT, end_date TEXT, feed TEXT, params_json TEXT, universe_json TEXT, summary_json TEXT);
    CREATE TABLE equity_curve (run_id TEXT, ts TEXT, equity REAL, cash REAL);
    CREATE TABLE features_live (symbol TEXT, ts TEXT, feed TEXT, day TEXT, candidate INTEGER, features_json TEXT, labels_json TEXT);`);
  const now = new Date().toISOString();
  db.prepare("INSERT INTO bot_state VALUES (?,?,?)").run("heartbeat", JSON.stringify({ ts: now, tick: 5, universe: 60, slots: { wave_rider: { mode: "live", positions: 1, trades: 1, realized: 3.5, paused: false } } }), now);
  db.prepare("INSERT INTO bot_state VALUES (?,?,?)").run("account", JSON.stringify({ equity: 100003.5, cash: 99000 }), now);
  db.prepare("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)").run("AAPL", "wave_rider", "live", 5, 100, now, 101, 100.8, null, null, null, now);
  db.prepare("INSERT INTO trades (run_id, mode, strategy, symbol, qty, entry_price, entry_time, exit_price, exit_time, exit_reason, peak_price, pnl, pnl_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)").run("live", "live", "wave_rider", "MSFT", 5, 200, now, 200.7, now, "wave_exit", 201, 3.5, 0.35);
  db.close();
  store = new Store(path.join(dir, "data", "t.db"));
  app = await buildServer(store);
});
afterAll(async () => { await app.close(); store.close(); });

describe("api", () => {
  it("health and status read the heartbeat", async () => {
    const h = await app.inject({ method: "GET", url: "/api/health" });
    expect(h.json().bot).toBe("running");
    const s = await app.inject({ method: "GET", url: "/api/status" });
    expect(s.json().account.equity).toBe(100003.5);
    expect(s.json().heartbeat.slots.wave_rider.trades).toBe(1);
  });
  it("positions, trades, strategies, reports", async () => {
    expect((await app.inject({ method: "GET", url: "/api/positions" })).json()).toHaveLength(1);
    const day = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
    expect((await app.inject({ method: "GET", url: `/api/trades?day=${day}` })).json()[0].symbol).toBe("MSFT");
    expect((await app.inject({ method: "GET", url: "/api/trades?mode=bogus" })).statusCode).toBe(400);
    const st = (await app.inject({ method: "GET", url: "/api/strategies" })).json();
    expect(st[0].id).toBe("wave_rider"); expect(st[0].live.realized).toBe(3.5);
    const reps = (await app.inject({ method: "GET", url: "/api/reports" })).json();
    expect(reps[0].files).toContain("0902-premarket.md");
    expect((await app.inject({ method: "GET", url: "/api/reports/2026-09-23/0902-premarket.md" })).json().markdown).toContain("hello");
    expect((await app.inject({ method: "GET", url: "/api/reports/2026-09-23/../secret.md" })).statusCode).not.toBe(200);
  });
  it("control requests are queued for the bot", async () => {
    const r = await app.inject({ method: "POST", url: "/api/controls", payload: { command: "pause", strategy: "wave_rider" } });
    expect(r.statusCode).toBe(200); expect(r.json().queued).toBe(true);
    const list = (await app.inject({ method: "GET", url: "/api/controls" })).json();
    expect(list[0].command).toBe("pause"); expect(list[0].status).toBe("pending");
    expect((await app.inject({ method: "POST", url: "/api/controls", payload: { command: "explode" } })).statusCode).toBe(400);
  });
});
