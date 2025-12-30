# Maestro Super API

FastAPI backend for construction plan analysis.

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="sqlite:///./local.db"
export DEV_USER_ID="dev-user-123"

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing
```

## Production Deployment

Deployed on Railway with Supabase Postgres.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| DATABASE_URL | Yes | SQLite or Postgres connection string |
| DEV_USER_ID | No | Bypasses auth for local dev |
| SUPABASE_JWT_SECRET | Prod | JWT validation secret |
| SUPABASE_URL | Prod | Supabase project URL |
| FRONTEND_URL | Prod | CORS origin for frontend |

### Deploy to Railway

1. Connect your repo to Railway
2. Set the root directory to `services/api`
3. Set environment variables in Railway dashboard
4. Railway will auto-deploy on push to main

### Verify Deployment

```bash
# After deployment
python scripts/verify_deployment.py https://your-app.up.railway.app
```

## API Documentation

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

## Project Structure

```
services/api/
├── alembic/              # Database migrations
├── app/
│   ├── auth/             # JWT validation, user context
│   ├── database/         # SQLAlchemy engine, session
│   ├── models/           # ORM models
│   ├── routers/          # API endpoints
│   ├── schemas/          # Pydantic request/response models
│   ├── services/         # Business logic (AI, storage)
│   ├── config.py         # Settings from environment
│   └── main.py           # FastAPI app entry point
├── scripts/              # Deployment utilities
├── tests/                # pytest tests
├── Dockerfile
├── railway.toml
└── requirements.txt
```
