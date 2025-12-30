import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key enforcement in SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


from app.models import (
    ContextPointer,
    DisciplineContext,
    PageContext,
    Project,
    ProjectFile,
    Query,
    UsageEvent,
)

# Ensure all models are imported so they're registered with Base.metadata
__all__ = [
    "ContextPointer",
    "DisciplineContext",
    "PageContext",
    "Project",
    "ProjectFile",
    "Query",
    "UsageEvent",
]


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
    from app.models.enums import ProjectStatus

    project = Project(
        user_id=test_user_id,
        name="Test Project",
        status=ProjectStatus.SETUP,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@pytest.fixture
def sample_file(session: Session, sample_project: Project) -> ProjectFile:
    """Create a sample PDF file for testing."""
    from app.models.enums import FileType

    file = ProjectFile(
        project_id=sample_project.id,
        name="test-plans.pdf",
        file_type=FileType.PDF,
        page_count=10,
        is_folder=False,
    )
    session.add(file)
    session.commit()
    session.refresh(file)
    return file


@pytest.fixture
def sample_pointer(session: Session, sample_file: ProjectFile) -> ContextPointer:
    """Create a sample context pointer for testing."""
    from app.models.enums import PointerStatus

    pointer = ContextPointer(
        file_id=sample_file.id,
        page_number=1,
        x_norm=0.1,
        y_norm=0.2,
        w_norm=0.3,
        h_norm=0.4,
        title="Test Pointer",
        description="A test context pointer",
        status=PointerStatus.COMPLETE,
    )
    session.add(pointer)
    session.commit()
    session.refresh(pointer)
    return pointer


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
