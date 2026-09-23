import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";

/** Where things live. The web app sits in <project>/web; the Python side owns the database and settings.
 *  Resolved on every call (not at import time) so tests can point it at a temporary folder. */
export function projectRoot(): string {
  return path.resolve(process.env.RTW_PROJECT_ROOT ?? path.join(process.cwd(), ".."));
}

export function loadSettings(): Record<string, any> {
  const primary = path.join(projectRoot(), "config", "settings.yaml");
  const example = path.join(projectRoot(), "config", "settings.example.yaml");
  const file = existsSync(primary) ? primary : example;
  return parse(readFileSync(file, "utf8"));
}

export function dbPath(): string {
  const s = loadSettings();
  const p: string = s?.storage?.db_path ?? "data/ridethewave.db";
  return path.isAbsolute(p) ? p : path.join(projectRoot(), p);
}

export function reportsDir(): string {
  const s = loadSettings();
  const p: string = s?.operator?.report_dir ?? "data/reports";
  return path.isAbsolute(p) ? p : path.join(projectRoot(), p);
}

export const API_TOKEN = process.env.RTW_API_TOKEN ?? "";
export const HOST = process.env.RTW_API_HOST ?? "127.0.0.1";
export const PORT = Number(process.env.RTW_API_PORT ?? 8787);
