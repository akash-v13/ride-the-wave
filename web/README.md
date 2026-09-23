# web

TypeScript HTTP API and web UI for Ride The Wave. The Python bot stays the owner of trading, data and
the database; this service reads the same SQLite file and queues control requests the bot applies on
its next tick.

- `src/server.ts`: Fastify app; serves `/api/*` and the static UI from `public/`.
- `src/routes/api.ts`: the endpoints (health, status, positions, trades, ledger, strategies, reports, backtests, features, controls).
- `src/db.ts`: `Store`: read-only connection for data, a separate writer only for `control_requests`.
- `src/config.ts`: finds the project root, settings and database; env `RTW_PROJECT_ROOT`, `RTW_API_HOST` (default 127.0.0.1), `RTW_API_PORT` (8787), `RTW_API_TOKEN` (required for POST when set).
- `public/`: the UI, plain HTML and JavaScript, refreshes every 5 seconds.
- `test/`: vitest, runs the API against a temporary database.

```bash
npm install && npm run build && npm start          # http://127.0.0.1:8787
npm run dev                                         # watch mode
npm test
```

Feature doc: `docs/features/18-typescript-api.md`.
