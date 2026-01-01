"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import disciplines, health, pages, pointers, projects, queries

settings = get_settings()

app = FastAPI(
    title="Maestro Super API",
    description="Construction plan analysis for superintendents",
    version="0.1.0",
    redirect_slashes=False,  # Prevent 307 redirects that break HTTPS through proxies
)

# CORS for frontend
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]

# Add production frontend URL if configured
if settings.frontend_url:
    origins.append(settings.frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(disciplines.router)
app.include_router(pages.router)
app.include_router(pointers.router)
app.include_router(queries.router)
