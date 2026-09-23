import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Store } from "./db.js";
import { registerApi } from "./routes/api.js";
import { HOST, PORT } from "./config.js";

const here = path.dirname(fileURLToPath(import.meta.url));

export async function buildServer(store: Store) {
  const app = Fastify({ logger: { level: process.env.RTW_LOG_LEVEL ?? "info" } });
  // must be set before routes and plugins are registered, or Fastify keeps its default handler
  app.setErrorHandler((err: unknown, _req, reply) => {
    const e = err as { statusCode?: number; issues?: unknown; name?: string; message?: string };
    const isValidation = e.name === "ZodError" || Array.isArray(e.issues);
    const code = isValidation ? 400 : (e.statusCode ?? 500);
    reply.code(code).send({ error: e.message ?? "error", issues: isValidation ? e.issues : undefined });
  });
  await registerApi(app, store);
  await app.register(fastifyStatic, { root: path.join(here, "..", "public"), prefix: "/" });
  return app;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const store = new Store();
  const app = await buildServer(store);
  await app.listen({ host: HOST, port: PORT });
  const shutdown = async () => { await app.close(); store.close(); process.exit(0); };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
