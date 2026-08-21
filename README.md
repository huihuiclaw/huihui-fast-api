# huihui-fast-api

A minimal FastAPI service packaged for Docker.

## Layout

```
huihui-fast-api/
├── app/
│   ├── api/
│   │   ├── admob.py        # /admob/earnings
│   │   ├── health.py       # /health, /ready
│   │   └── routes.py       # top-level APIRouter
│   ├── services/
│   │   └── admob.py        # AdMob client + OAuth refresh
│   ├── config.py           # pydantic-settings
│   └── main.py             # FastAPI app factory
├── tests/
│   └── test_health.py
├── .github/
│   └── workflows/
│       └── test.yml        # CI smoke test (verifies secrets wiring)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── .dockerignore
```

## Local dev (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in your AdMob secrets
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive Swagger UI.

## Run with Docker

```bash
docker compose up --build
```

The service will be available at <http://localhost:8000>.

## Endpoints

| Method | Path             | Purpose                                |
| ------ | ---------------- | -------------------------------------- |
| GET    | `/`              | Friendly hello                         |
| GET    | `/health`        | Liveness probe                         |
| GET    | `/ready`         | Readiness probe with app metadata       |
| GET    | `/admob/earnings`| AdMob earnings (default 7 days, max 90)|
| GET    | `/docs`          | Swagger UI (auto-generated)            |

### `GET /admob/earnings?days=N`

Returns per-day rows plus totals:

```json
{
  "days": 7,
  "rows": [
    {"date": "08/15", "earnings_usd": 0.45, "impressions": 473, "clicks": 9}
  ],
  "totals": {"earnings_usd": 6.80, "impressions": 12345, "clicks": 234},
  "fetched_at": "2026-08-21T07:00:00+00:00"
}
```

## Secrets

The AdMob client reads from environment variables. In production these are stored
as GitHub Secrets; locally they live in `.env` (git-ignored).

| Variable             | Source                       |
| -------------------- | ---------------------------- |
| `ADMOB_CLIENT_ID`    | Google Cloud OAuth client    |
| `ADMOB_CLIENT_SECRET`| Google Cloud OAuth client    |
| `ADMOB_REFRESH_TOKEN`| AdMob OAuth grant            |
| `ADMOB_PUBLISHER_ID` | AdMob account id             |
| `ADMOB_ACCESS_TOKEN` | (optional) cached token      |
| `ADMOB_EXPIRY_DATE`  | (optional) ms since epoch    |

The client refreshes `ADMOB_ACCESS_TOKEN` automatically ~5 minutes before
expiry using the refresh token + client credentials.

## CI

`.github/workflows/test.yml` boots the container, hits each endpoint, and
verifies the AdMob wiring works with the secrets attached to the repo.

## Configuration

Copy `.env.example` to `.env` and tweak:

```env
APP_ENV=development
LOG_LEVEL=info
APP_NAME=huihui-fast-api
```

Settings are loaded via `pydantic-settings` and cached for the process lifetime.

## Tests

```bash
pip install httpx pytest
pytest
```