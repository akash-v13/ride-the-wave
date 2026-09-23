import type { FastifyInstance } from "fastify";
import { readdirSync, readFileSync, existsSync, statSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { Store } from "../db.js";
import { API_TOKEN, loadSettings, reportsDir } from "../config.js";

const ET = "America/New_York";

function etDay(d = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: ET, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

function etDayBoundsUtc(day: string): { start: string; end: string } {
  // day is YYYY-MM-DD in ET; find the UTC instants for local midnight and next midnight
  const probe = new Date(`${day}T12:00:00Z`);
  const offsetMin = etOffsetMinutes(probe);
  const start = new Date(Date.parse(`${day}T00:00:00Z`) - offsetMin * 60_000);
  const end = new Date(start.getTime() + 24 * 3600_000);
  return { start: start.toISOString(), end: end.toISOString() };
}

function etOffsetMinutes(d: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: ET, hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(d);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second"));
  return (asUtc - d.getTime()) / 60_000;
}

export function botStatus(store: Store, staleSeconds: number) {
  const hb = store.state("heartbeat");
  const value = (hb?.value ?? {}) as Record<string, any>;
  const ts = value.ts ?? hb?.updatedAt;
  const ageSec = ts ? (Date.now() - Date.parse(ts)) / 1000 : null;
  let status = "never run";
  if (ts && value.waiting_for) status = "waiting for open";
  else if (ageSec != null) status = ageSec < staleSeconds ? "running" : "stopped";
  return { status, lastTick: ts ?? null, ageSeconds: ageSec, heartbeat: value };
}

export async function registerApi(app: FastifyInstance, store: Store) {
  const settings = loadSettings();
  const staleSeconds: number = settings?.operator?.heartbeat_stale_seconds ?? 90;

  app.get("/api/health", async () => {
    const s = botStatus(store, staleSeconds);
    const risk = store.state("risk")?.value as Record<string, any> | null;
    const check = store.state("last_health_check")?.value as Record<string, any> | null;
    return { ok: true, bot: s.status, lastTick: s.lastTick, ageSeconds: s.ageSeconds, halted: risk?.halted ?? null, alerts: check?.alerts ?? [] };
  });

  app.get("/api/status", async () => {
    const s = botStatus(store, staleSeconds);
    return {
      bot: s.status,
      lastTick: s.lastTick,
      heartbeat: s.heartbeat,
      run: store.state("run")?.value ?? null,
      account: store.state("account")?.value ?? null,
      allocation: store.state("allocation")?.value ?? settings?.capital?.base_allocation ?? null,
      risk: store.state("risk")?.value ?? null,
      strategies: store.state("strategies")?.value ?? null,
      operatorTick: store.state("operator_tick")?.value ?? null,
      today: etDay(),
    };
  });

  app.get("/api/positions", async () => store.positions());

  app.get("/api/trades", async (req) => {
    const q = z.object({
      day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
      strategy: z.string().optional(),
      mode: z.enum(["live", "shadow", "backtest"]).optional(),
      limit: z.coerce.number().int().min(1).max(2000).default(200),
    }).parse(req.query);
    const bounds = q.day ? etDayBoundsUtc(q.day) : undefined;
    return store.trades({ since: bounds?.start, until: bounds?.end, strategy: q.strategy, mode: q.mode, limit: q.limit });
  });

  app.get("/api/ledger", async (req) => {
    const q = z.object({ strategy: z.string().optional(), run_id: z.string().default("live") }).parse(req.query);
    return store.ledger({ runId: q.run_id, strategy: q.strategy });
  });

  app.get("/api/strategies", async () => {
    const hb = (store.state("heartbeat")?.value ?? {}) as Record<string, any>;
    const slots = (hb.slots ?? {}) as Record<string, any>;
    const configured = (settings?.strategies ?? []) as Array<Record<string, any>>;
    return configured.map((c) => ({ id: c.id, kind: c.kind, mode: c.mode ?? "shadow", enabled: c.enabled ?? true, weight: c.weight ?? 1, params: c.params ?? {}, live: slots[c.id] ?? null }));
  });

  app.get("/api/reports", async () => {
    const root = reportsDir();
    if (!existsSync(root)) return [];
    const days = readdirSync(root).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d) && statSync(path.join(root, d)).isDirectory()).sort().reverse();
    return days.map((day) => ({ day, files: readdirSync(path.join(root, day)).filter((f) => f.endsWith(".md")).sort().reverse() }));
  });

  app.get("/api/reports/latest", async () => {
    const f = path.join(reportsDir(), "latest.md");
    return existsSync(f) ? { markdown: readFileSync(f, "utf8") } : { markdown: "" };
  });

  app.get("/api/reports/:day/:file", async (req, reply) => {
    const p = z.object({ day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), file: z.string().regex(/^[\w-]+\.md$/) }).parse(req.params);
    const f = path.join(reportsDir(), p.day, p.file);
    if (!existsSync(f)) return reply.code(404).send({ error: "not found" });
    return { markdown: readFileSync(f, "utf8") };
  });

  app.get("/api/backtests", async () => store.backtests().map((r: any) => ({ ...r, summary: r.summary_json ? JSON.parse(r.summary_json) : null, universe: JSON.parse(r.universe_json ?? "[]"), summary_json: undefined, universe_json: undefined })));
  app.get("/api/backtests/:id/equity", async (req) => store.equityCurve((req.params as any).id));

  app.get("/api/features/today", async () => ({ day: etDay(), ...(store.featureCounts(etDay()) as object) }));

  app.get("/api/controls", async () => store.controls());

  app.post("/api/controls", async (req, reply) => {
    if (API_TOKEN) {
      const auth = (req.headers.authorization ?? "").replace(/^Bearer\s+/i, "");
      if (auth !== API_TOKEN) return reply.code(401).send({ error: "unauthorized" });
    }
    const body = z.object({ command: z.enum(["pause", "resume", "flatten", "halt"]), strategy: z.string().default("all") }).parse(req.body);
    const id = store.submitControl(body.command, body.strategy === "all" ? null : body.strategy);
    return { id, queued: true, note: "applied by the bot on its next tick (within about 15 seconds while running)" };
  });
}
