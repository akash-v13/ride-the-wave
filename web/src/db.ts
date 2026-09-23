import { DatabaseSync } from "node:sqlite";
import { dbPath } from "./config.js";

/**
 * Node's built-in SQLite (no native build). Two connections: read-only for everything the UI shows,
 * and a writer used only for control_requests. The Python bot owns the schema; this side creates
 * control_requests only if the bot never has.
 */
export class Store {
  readonly ro: DatabaseSync;
  private rw: DatabaseSync | null = null;
  constructor(readonly file: string = dbPath()) {
    this.ro = new DatabaseSync(file, { readOnly: true });
    this.ro.exec("PRAGMA busy_timeout = 2000");
  }

  private writer(): DatabaseSync {
    if (!this.rw) {
      this.rw = new DatabaseSync(this.file);
      this.rw.exec("PRAGMA busy_timeout = 5000");
      this.rw.exec(`CREATE TABLE IF NOT EXISTS control_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, command TEXT NOT NULL, strategy TEXT,
        source TEXT NOT NULL DEFAULT 'api', status TEXT NOT NULL DEFAULT 'pending', result TEXT, handled_at TEXT)`);
    }
    return this.rw;
  }

  state(key: string): { value: unknown; updatedAt: string } | null {
    const row = this.ro.prepare("SELECT value, updated_at FROM bot_state WHERE key = ?").get(key) as
      | { value: string | null; updated_at: string }
      | undefined;
    if (!row) return null;
    return { value: row.value == null ? null : JSON.parse(row.value), updatedAt: row.updated_at };
  }

  positions() {
    return this.ro.prepare("SELECT * FROM positions ORDER BY entry_time").all();
  }

  trades(opts: { since?: string; until?: string; strategy?: string; mode?: string; limit?: number }) {
    const where: string[] = [];
    const args: (string | number)[] = [];
    if (opts.since) { where.push("exit_time >= ?"); args.push(opts.since); }
    if (opts.until) { where.push("exit_time < ?"); args.push(opts.until); }
    if (opts.strategy) { where.push("strategy = ?"); args.push(opts.strategy); }
    if (opts.mode) { where.push("mode = ?"); args.push(opts.mode); }
    const sql = `SELECT * FROM trades ${where.length ? "WHERE " + where.join(" AND ") : ""} ORDER BY exit_time DESC LIMIT ?`;
    return this.ro.prepare(sql).all(...args, opts.limit ?? 200);
  }

  ledger(opts: { runId?: string; strategy?: string }) {
    const where = ["run_id = ?"];
    const args: string[] = [opts.runId ?? "live"];
    if (opts.strategy) { where.push("strategy = ?"); args.push(opts.strategy); }
    return this.ro.prepare(`SELECT * FROM daily_ledger WHERE ${where.join(" AND ")} ORDER BY date DESC, strategy`).all(...args);
  }

  backtests(limit = 30) {
    return this.ro.prepare("SELECT id, created_at, start_date, end_date, feed, universe_json, summary_json FROM backtest_runs ORDER BY created_at DESC LIMIT ?").all(limit);
  }

  equityCurve(runId: string) {
    return this.ro.prepare("SELECT ts, equity, cash FROM equity_curve WHERE run_id = ? ORDER BY ts").all(runId);
  }

  featureCounts(day: string) {
    return this.ro.prepare("SELECT COUNT(*) AS rows, COALESCE(SUM(candidate),0) AS candidates, COALESCE(SUM(labels_json IS NOT NULL),0) AS labelled FROM features_live WHERE day = ?").get(day);
  }

  controls(limit = 20) {
    try {
      return this.ro.prepare("SELECT * FROM control_requests ORDER BY id DESC LIMIT ?").all(limit);
    } catch {
      return [];
    }
  }

  submitControl(command: string, strategy: string | null, source = "api"): number {
    const res = this.writer()
      .prepare("INSERT INTO control_requests (created_at, command, strategy, source) VALUES (?, ?, ?, ?)")
      .run(new Date().toISOString(), command, strategy, source);
    return Number(res.lastInsertRowid);
  }

  close() {
    this.ro.close();
    this.rw?.close();
  }
}
