# huihui-fast-api

A minimal FastAPI service packaged for Docker.

## Layout

```
huihui-fast-api/
├── app/
│   ├── api/
│   │   ├── health.py      # /health, /ready
│   │   └── routes.py      # top-level APIRouter
│   ├── config.py          # pydantic-settings
│   └── main.py            # FastAPI app factory
├── tests/
│   └── test_health.py
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
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive Swagger UI.

## Run with Docker

```bash
docker compose up --build
```

The service will be available at <http://localhost:8000>.

## Endpoints

| Method | Path     | Purpose                          |
| ------ | -------- | -------------------------------- |
| GET    | `/`      | Friendly hello                   |
| GET    | `/health`| Liveness probe                   |
| GET    | `/ready` | Readiness probe with app metadata |
| GET    | `/docs`  | Swagger UI (auto-generated)      |

## Tests

```bash
pip install httpx
pytest
```

## Configuration

Copy `.env.example` to `.env` and tweak:

```env
APP_ENV=development
LOG_LEVEL=info
APP_NAME=huihui-fast-api
```

Settings are loaded via `pydantic-settings` and cached for the process lifetime.