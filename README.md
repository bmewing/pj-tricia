# PJ Tricia

Online trivia nights: make a group, schedule a game, pick a host, and play from home. One
signed-in account is one team (a couple on one phone is fine); anyone else can watch.

- `backend/` — FastAPI, SQLAlchemy 2 (async), Alembic, Postgres (Neon)
- `frontend/` — React, Vite, TypeScript, Mantine, TanStack Query, Kinde
- `functions/` — packages the backend as a DigitalOcean function for deployment

## The game

| Round | Questions | Points each | Then |
| --- | --- | --- | --- |
| 1 | multiple choice | 5 | Double Down Dare |
| 2 | multiple choice | 10 | Double Down Dare |
| 3 | multiple choice | 15 | Double Down Dare |
| 4 | free-form | 20 | Do or Die Dare (wager) |

- **Double Down Dare:** a free-form question teams can pass on. Right doubles the round's points;
  wrong zeroes them; passing keeps them.
- **Do or Die Dare:** teams wager 0 up to their total before seeing the question, then win or
  lose it. A blank answer counts as wrong.
- Multiple choice grades itself. Free-form answers that match exactly (ignoring case,
  punctuation and a leading "the/a/an") are marked right automatically; the host marks the
  rest, and can change any grade until the game ends.
- Scores are worked out only on the server (`backend/app/game/scoring.py`). Nobody but the host
  sees a question before it's reached or an answer before it's revealed, and scores leave out
  the question that's still open, so they never give an answer away.

The host writes the questions (in the editor, or by importing CSV: `round, kind, question, A,
B, C, D, answer`). Changing the host after questions exist asks whether to keep or clear them.

Live updates are polling: clients call `GET /api/events/{id}/live?since=<version>` every 1.5–4
seconds and get a bare 204 when nothing changed.

## Look

The branding (logo, colors, the billboard question cards, the dare names and the house rules)
comes from the PJ Tricia Keynote deck. The logo and lightbulb icon in `frontend/public` were cut
from it. Headings use Marker Felt on Apple devices and Permanent Marker elsewhere.

## Running locally

Needs [uv](https://docs.astral.sh/uv/) and Node.js 24+.

`backend/.env` (see `.env.example`) points at the `pjtricia_dev` database on Neon and the
Kinde business; `frontend/.env.local` holds the Kinde domain, client ID and audience. None of
the Kinde values are secret.

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API docs are at http://localhost:8000/api/docs.

## Checks

The backend tests rebuild their own `pjtricia_pytest` schema in whatever `DATABASE_URL`
points at, so they never touch the dev tables.

```bash
cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
```

```bash
cd frontend && npm run format:check && npm run lint && npm run typecheck && npm test
```

After changing an endpoint, regenerate the frontend's API types from `frontend/` with
`npm run gen:api`.

## Deployment

DigitalOcean App Platform (`.do/app.yaml`): the frontend as a static site and the API as one
function, `core/app`, at `/api/core/app/...` (`backend/app/serverless.py` adapts requests).

- After changing `backend/app`, refresh the function's copy: `bash functions/sync_backend.sh`.
- After changing backend dependencies, from `backend/`:
  `uv export --no-default-groups --no-hashes --no-emit-project --no-header --format requirements-txt -o ../functions/packages/core/app/requirements.txt`
- Run migrations against production yourself before deploying code that needs them. The
  repo-root `.env` (gitignored) holds Neon's direct (`DATABASE_URL`) and pooled
  (`DATABASE_URL_POOLED`) strings for the production `neondb` database:
  `cd backend && uv run --env-file ../.env alembic upgrade head`
- The function's `DATABASE_URL` secret is the **pooled** string; `SERVERLESS=true` turns off
  connection pooling and prepared-statement caching to suit it.
- Kinde: the "PJ Tricia" application and "PJ Tricia API" (audience `https://api.pjtricia`) live
  in their own Kinde business, `pjtricia.kinde.com`. The app's callback and logout URLs are
  localhost:5173 and https://pj-tricia-d5gcc.ondigitalocean.app; add any new domain there too.
- The function has 512 MB: CPU scales with memory, and at 256 MB a cold start outran the
  timeout.
