import pytest
from fastapi.testclient import TestClient
from sqlalchemy import ARRAY, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.models  # noqa: F401 - ensure all model tables are registered on Base.metadata
from app.models.project import Project


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key enforcement in SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """Allow PostgreSQL JSONB columns to be created in SQLite test DBs."""
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    """Allow PostgreSQL ARRAY columns to be created in SQLite test DBs."""
    return "JSON"


try:
    from pgvector.sqlalchemy.vector import VECTOR

    @compiles(VECTOR, "sqlite")
    def _compile_vector_sqlite(type_, compiler, **kw):
        """Allow pgvector columns to be created in SQLite test DBs."""
        return "BLOB"
except Exception:
    pass


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing.

    Uses StaticPool to ensure all connections share the same in-memory database.
    Without this, each connection would get a fresh database without tables.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    # Enable foreign key enforcement in SQLite
    event.listen(engine, "connect", _set_sqlite_pragma)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(engine) -> Session:
    """Create a test database session."""
    TestSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )
    session = TestSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def test_user_id() -> str:
    """Provide a consistent test user ID."""
    return "test-user-00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_project(session: Session, test_user_id: str) -> Project:
    """Create a sample project for testing."""
    project = Project(
        user_id=test_user_id,
        name="Test Project",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@pytest.fixture
def client(engine, test_user_id: str) -> TestClient:
    """
    Create a FastAPI test client with in-memory database.

    Uses dev mode auth bypass (DEV_USER_ID).
    """
    from sqlalchemy.orm import sessionmaker

    # Import get_db from the same place routers import it
    from app.database import session as session_module
    from app.main import app

    # Create session factory bound to test engine
    TestSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Override the get_db function that routers use
    app.dependency_overrides[session_module.get_db] = override_get_db

    # Mock auth to use test user
    from app.auth import dependencies as auth_deps
    from app.auth.schemas import User

    def override_get_current_user() -> User:
        return User(id=test_user_id, email="test@test.com")

    app.dependency_overrides[auth_deps.get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    # Clear overrides after test
    app.dependency_overrides.clear()
