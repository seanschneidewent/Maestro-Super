"""Test SQLAlchemy models."""

import pytest
from sqlalchemy.orm import Session

from app.models import (
    ContextPointer,
    DisciplineContext,
    PageContext,
    Project,
    ProjectFile,
    Query,
    UsageEvent,
)
from app.models.enums import (
    DisciplineStatus,
    EventType,
    FileType,
    PointerStatus,
    ProcessingStatus,
    ProjectStatus,
)


class TestProject:
    """Test Project model."""

    def test_create_project(self, session: Session, test_user_id: str):
        """Test creating a project."""
        project = Project(
            user_id=test_user_id,
            name="Test Project",
            status=ProjectStatus.SETUP,
        )
        session.add(project)
        session.commit()

        assert project.id is not None
        assert len(project.id) == 36  # UUID format
        assert project.user_id == test_user_id
        assert project.name == "Test Project"
        assert project.status == ProjectStatus.SETUP
        assert project.created_at is not None
        assert project.updated_at is not None

    def test_project_default_status(self, session: Session, test_user_id: str):
        """Test project defaults to SETUP status."""
        project = Project(user_id=test_user_id, name="Default Status")
        session.add(project)
        session.commit()

        assert project.status == ProjectStatus.SETUP


class TestProjectFile:
    """Test ProjectFile model."""

    def test_create_file(self, session: Session, sample_project: Project):
        """Test creating a project file."""
        file = ProjectFile(
            project_id=sample_project.id,
            name="plans.pdf",
            file_type=FileType.PDF,
            page_count=25,
            storage_path="projects/123/plans.pdf",
        )
        session.add(file)
        session.commit()

        assert file.id is not None
        assert file.project_id == sample_project.id
        assert file.name == "plans.pdf"
        assert file.file_type == FileType.PDF
        assert file.page_count == 25
        assert file.is_folder is False

    def test_folder_hierarchy(self, session: Session, sample_project: Project):
        """Test nested folder structure."""
        folder = ProjectFile(
            project_id=sample_project.id,
            name="Drawings",
            file_type=FileType.PDF,
            is_folder=True,
        )
        session.add(folder)
        session.commit()

        child_file = ProjectFile(
            project_id=sample_project.id,
            name="A-101.pdf",
            file_type=FileType.PDF,
            parent_id=folder.id,
        )
        session.add(child_file)
        session.commit()

        session.refresh(folder)
        assert len(folder.children) == 1
        assert folder.children[0].name == "A-101.pdf"
        assert child_file.parent_id == folder.id

    def test_cascade_delete_folder(self, session: Session, sample_project: Project):
        """Test cascade delete when folder is deleted."""
        folder = ProjectFile(
            project_id=sample_project.id,
            name="Folder",
            file_type=FileType.PDF,
            is_folder=True,
        )
        session.add(folder)
        session.commit()

        child = ProjectFile(
            project_id=sample_project.id,
            name="Child.pdf",
            file_type=FileType.PDF,
            parent_id=folder.id,
        )
        session.add(child)
        session.commit()
        child_id = child.id

        # Delete folder
        session.delete(folder)
        session.commit()

        # Expire session cache to force fresh query
        session.expire_all()

        # Child should be deleted too
        assert session.get(ProjectFile, child_id) is None


class TestContextPointer:
    """Test ContextPointer model."""

    def test_create_pointer(self, session: Session, sample_file: ProjectFile):
        """Test creating a context pointer."""
        pointer = ContextPointer(
            file_id=sample_file.id,
            page_number=3,
            x_norm=0.1,
            y_norm=0.2,
            w_norm=0.3,
            h_norm=0.4,
            title="Panel Schedule",
            description="Electrical panel P-101",
        )
        session.add(pointer)
        session.commit()

        assert pointer.id is not None
        assert pointer.page_number == 3
        assert pointer.x_norm == 0.1
        assert pointer.status == PointerStatus.GENERATING
        assert pointer.committed_at is None
        assert pointer.is_committed is False

    def test_bounds_property(self, session: Session, sample_file: ProjectFile):
        """Test bounds dictionary property."""
        pointer = ContextPointer(
            file_id=sample_file.id,
            page_number=1,
            x_norm=0.1,
            y_norm=0.2,
            w_norm=0.3,
            h_norm=0.4,
        )
        session.add(pointer)
        session.commit()

        bounds = pointer.bounds
        assert bounds == {
            "xNorm": 0.1,
            "yNorm": 0.2,
            "wNorm": 0.3,
            "hNorm": 0.4,
        }

    def test_jsonb_columns(self, session: Session, sample_file: ProjectFile):
        """Test JSONB columns work correctly."""
        pointer = ContextPointer(
            file_id=sample_file.id,
            page_number=1,
            x_norm=0.1,
            y_norm=0.2,
            w_norm=0.3,
            h_norm=0.4,
            ai_elements=[
                {"name": "Panel P-101", "type": "equipment", "details": "200A main"},
                {"name": "Circuit 1", "type": "circuit", "details": "20A"},
            ],
            text_content={
                "textElements": [
                    {"id": "native_1", "text": "PANEL SCHEDULE"},
                    {"id": "ocr_1", "text": "200A MAIN"},
                ]
            },
        )
        session.add(pointer)
        session.commit()

        session.refresh(pointer)
        assert len(pointer.ai_elements) == 2
        assert pointer.ai_elements[0]["name"] == "Panel P-101"
        assert pointer.text_content["textElements"][0]["text"] == "PANEL SCHEDULE"


class TestPageContext:
    """Test PageContext model."""

    def test_create_page_context(self, session: Session, sample_file: ProjectFile):
        """Test creating page context."""
        page = PageContext(
            file_id=sample_file.id,
            page_number=1,
            sheet_number="E-2.1",
            discipline_code="E",
        )
        session.add(page)
        session.commit()

        assert page.id is not None
        assert page.processing_status == ProcessingStatus.UNPROCESSED
        assert page.retry_count == 0

    def test_unique_constraint(self, session: Session, sample_file: ProjectFile):
        """Test unique constraint on file_id + page_number."""
        page1 = PageContext(file_id=sample_file.id, page_number=1)
        session.add(page1)
        session.commit()

        page2 = PageContext(file_id=sample_file.id, page_number=1)
        session.add(page2)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()


class TestDisciplineContext:
    """Test DisciplineContext model."""

    def test_create_discipline_context(self, session: Session, sample_project: Project):
        """Test creating discipline context."""
        discipline = DisciplineContext(
            project_id=sample_project.id,
            code="E",
            name="Electrical",
        )
        session.add(discipline)
        session.commit()

        assert discipline.id is not None
        assert discipline.processing_status == DisciplineStatus.WAITING

    def test_discipline_name_lookup(self):
        """Test discipline name lookup."""
        assert DisciplineContext.get_discipline_name("E") == "Electrical"
        assert DisciplineContext.get_discipline_name("M") == "Mechanical"
        assert DisciplineContext.get_discipline_name("FP") == "Fire Protection"
        assert DisciplineContext.get_discipline_name("X") == "Unknown"


class TestQuery:
    """Test Query model."""

    def test_create_query(
        self, session: Session, sample_project: Project, test_user_id: str
    ):
        """Test creating a query."""
        query = Query(
            user_id=test_user_id,
            project_id=sample_project.id,
            query_text="Where are the electrical panels?",
            response_text="Based on the plans, panels are on sheet E-2.1...",
            tokens_used=1500,
        )
        session.add(query)
        session.commit()

        assert query.id is not None
        assert query.created_at is not None


class TestUsageEvent:
    """Test UsageEvent model."""

    def test_create_usage_event(self, session: Session, test_user_id: str):
        """Test creating a usage event."""
        event = UsageEvent(
            user_id=test_user_id,
            event_type=EventType.GEMINI_EXTRACTION,
            tokens_input=1000,
            tokens_output=500,
            cost_cents=5,
            event_metadata={"file_id": "abc123", "page": 1},
        )
        session.add(event)
        session.commit()

        assert event.id is not None
        assert event.event_type == EventType.GEMINI_EXTRACTION
        assert event.cost_cents == 5
        assert event.event_metadata["file_id"] == "abc123"


class TestCascadeDeletes:
    """Test cascade delete behavior."""

    def test_cascade_delete_project(
        self, session: Session, sample_project: Project, sample_file: ProjectFile
    ):
        """Test deleting project cascades to files."""
        project_id = sample_project.id
        file_id = sample_file.id

        session.delete(sample_project)
        session.commit()

        # Expire session cache to force fresh query
        session.expire_all()

        assert session.get(Project, project_id) is None
        assert session.get(ProjectFile, file_id) is None

    def test_cascade_delete_file(
        self, session: Session, sample_file: ProjectFile, sample_pointer: ContextPointer
    ):
        """Test deleting file cascades to pointers."""
        file_id = sample_file.id
        pointer_id = sample_pointer.id

        session.delete(sample_file)
        session.commit()

        # Expire session cache to force fresh query
        session.expire_all()

        assert session.get(ProjectFile, file_id) is None
        assert session.get(ContextPointer, pointer_id) is None
