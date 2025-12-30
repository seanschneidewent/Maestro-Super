"""Tests for API routes."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test GET /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestProjectsRouter:
    """Test projects CRUD endpoints."""

    def test_create_project(self, client: TestClient):
        """Test POST /projects creates a new project."""
        response = client.post("/projects/", json={"name": "Test Project"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["status"] == "setup"
        assert "id" in data
        assert "createdAt" in data

    def test_list_projects(self, client: TestClient):
        """Test GET /projects returns user's projects."""
        # Create some projects
        client.post("/projects/", json={"name": "Project 1"})
        client.post("/projects/", json={"name": "Project 2"})

        response = client.get("/projects/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Project 1"
        assert data[1]["name"] == "Project 2"

    def test_get_project(self, client: TestClient):
        """Test GET /projects/{id} returns specific project."""
        create_response = client.post("/projects/", json={"name": "My Project"})
        project_id = create_response.json()["id"]

        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "My Project"

    def test_get_project_not_found(self, client: TestClient):
        """Test GET /projects/{id} returns 404 for non-existent project."""
        response = client.get("/projects/nonexistent-id")
        assert response.status_code == 404

    def test_update_project(self, client: TestClient):
        """Test PATCH /projects/{id} updates project."""
        create_response = client.post("/projects/", json={"name": "Original"})
        project_id = create_response.json()["id"]

        response = client.patch(
            f"/projects/{project_id}",
            json={"name": "Updated", "status": "ready"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["status"] == "ready"

    def test_delete_project(self, client: TestClient):
        """Test DELETE /projects/{id} removes project."""
        create_response = client.post("/projects/", json={"name": "To Delete"})
        project_id = create_response.json()["id"]

        # Delete
        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 204

        # Verify gone
        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 404


class TestFilesRouter:
    """Test files CRUD endpoints."""

    def test_create_file(self, client: TestClient):
        """Test POST /projects/{id}/files creates a file."""
        # Create project first
        project = client.post("/projects/", json={"name": "Test"}).json()

        response = client.post(
            f"/projects/{project['id']}/files",
            json={
                "name": "plans.pdf",
                "fileType": "pdf",
                "pageCount": 10,
                "isFolder": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "plans.pdf"
        assert data["fileType"] == "pdf"
        assert data["pageCount"] == 10
        assert data["isFolder"] is False

    def test_create_folder(self, client: TestClient):
        """Test creating a folder."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        response = client.post(
            f"/projects/{project['id']}/files",
            json={
                "name": "Drawings",
                "fileType": "pdf",  # FileType required even for folders
                "isFolder": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["isFolder"] is True

    def test_create_file_in_folder(self, client: TestClient):
        """Test creating a file inside a folder."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        # Create folder
        folder = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "Drawings", "fileType": "pdf", "isFolder": True},
        ).json()

        # Create file in folder
        response = client.post(
            f"/projects/{project['id']}/files",
            json={
                "name": "plans.pdf",
                "fileType": "pdf",
                "parentId": folder["id"],
            },
        )
        assert response.status_code == 201
        assert response.json()["parentId"] == folder["id"]

    def test_list_files_flat(self, client: TestClient):
        """Test listing files in flat mode."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        client.post(
            f"/projects/{project['id']}/files",
            json={"name": "file1.pdf", "fileType": "pdf"},
        )
        client.post(
            f"/projects/{project['id']}/files",
            json={"name": "file2.pdf", "fileType": "pdf"},
        )

        response = client.get(f"/projects/{project['id']}/files")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_files_tree(self, client: TestClient):
        """Test listing files in tree mode."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        # Create folder and nested file
        folder = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "Folder", "fileType": "pdf", "isFolder": True},
        ).json()
        client.post(
            f"/projects/{project['id']}/files",
            json={"name": "nested.pdf", "fileType": "pdf", "parentId": folder["id"]},
        )

        response = client.get(f"/projects/{project['id']}/files/tree")
        assert response.status_code == 200
        data = response.json()
        # Root should have the folder
        assert len(data) == 1
        assert data[0]["name"] == "Folder"
        assert data[0]["children"] is not None
        assert len(data[0]["children"]) == 1
        assert data[0]["children"][0]["name"] == "nested.pdf"

    def test_get_file(self, client: TestClient):
        """Test GET /files/{id} returns specific file."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "test.pdf", "fileType": "pdf"},
        ).json()

        response = client.get(f"/files/{file['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "test.pdf"

    def test_update_file(self, client: TestClient):
        """Test PATCH /files/{id} updates file."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "original.pdf", "fileType": "pdf"},
        ).json()

        response = client.patch(
            f"/files/{file['id']}",
            json={"name": "updated.pdf"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated.pdf"

    def test_delete_file(self, client: TestClient):
        """Test DELETE /files/{id} removes file."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "delete-me.pdf", "fileType": "pdf"},
        ).json()

        response = client.delete(f"/files/{file['id']}")
        assert response.status_code == 204

        # Verify gone
        response = client.get(f"/files/{file['id']}")
        assert response.status_code == 404

    def test_delete_folder_cascades(self, client: TestClient):
        """Test deleting folder also deletes children."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        folder = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "Folder", "fileType": "pdf", "isFolder": True},
        ).json()
        child = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "child.pdf", "fileType": "pdf", "parentId": folder["id"]},
        ).json()

        # Delete folder
        client.delete(f"/files/{folder['id']}")

        # Child should be gone too
        response = client.get(f"/files/{child['id']}")
        assert response.status_code == 404


class TestPointersRouter:
    """Test context pointers CRUD endpoints."""

    def test_create_pointer(self, client: TestClient):
        """Test POST /files/{id}/pointers creates a pointer."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()

        response = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {
                    "xNorm": 0.1,
                    "yNorm": 0.2,
                    "wNorm": 0.3,
                    "hNorm": 0.4,
                },
                "title": "Test Pointer",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["pageNumber"] == 1
        assert data["bounds"]["xNorm"] == 0.1
        assert data["title"] == "Test Pointer"
        assert data["status"] == "generating"

    def test_list_pointers(self, client: TestClient):
        """Test GET /files/{id}/pointers returns file's pointers."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()

        # Create pointers
        client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.1, "wNorm": 0.2, "hNorm": 0.2},
            },
        )
        client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 2,
                "bounds": {"xNorm": 0.3, "yNorm": 0.3, "wNorm": 0.2, "hNorm": 0.2},
            },
        )

        response = client.get(f"/files/{file['id']}/pointers")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_pointers_filter_by_page(self, client: TestClient):
        """Test filtering pointers by page number."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()

        # Create pointers on different pages
        client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.1, "wNorm": 0.2, "hNorm": 0.2},
            },
        )
        client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 2,
                "bounds": {"xNorm": 0.3, "yNorm": 0.3, "wNorm": 0.2, "hNorm": 0.2},
            },
        )

        response = client.get(f"/files/{file['id']}/pointers?page=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pageNumber"] == 1

    def test_get_pointer(self, client: TestClient):
        """Test GET /pointers/{id} returns specific pointer."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        response = client.get(f"/pointers/{pointer['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == pointer["id"]

    def test_update_pointer(self, client: TestClient):
        """Test PATCH /pointers/{id} updates pointer."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        response = client.patch(
            f"/pointers/{pointer['id']}",
            json={
                "title": "Updated Title",
                "status": "complete",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["status"] == "complete"

    def test_commit_pointer(self, client: TestClient):
        """Test POST /pointers/{id}/commit marks pointer as committed."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        assert pointer.get("committedAt") is None

        response = client.post(f"/pointers/{pointer['id']}/commit")
        assert response.status_code == 200
        assert response.json()["committedAt"] is not None

    def test_commit_pointer_twice_fails(self, client: TestClient):
        """Test committing already committed pointer fails."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        # First commit succeeds
        client.post(f"/pointers/{pointer['id']}/commit")

        # Second commit fails
        response = client.post(f"/pointers/{pointer['id']}/commit")
        assert response.status_code == 400

    def test_delete_pointer(self, client: TestClient):
        """Test DELETE /pointers/{id} removes pointer."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "plans.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        response = client.delete(f"/pointers/{pointer['id']}")
        assert response.status_code == 204

        # Verify gone
        response = client.get(f"/pointers/{pointer['id']}")
        assert response.status_code == 404


class TestQueriesRouter:
    """Test queries CRUD endpoints."""

    def test_create_query(self, client: TestClient):
        """Test POST /projects/{id}/queries creates a query."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        response = client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "What is the electrical load on this floor?"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["queryText"] == "What is the electrical load on this floor?"
        assert data["responseText"] is None  # Not yet processed by AI

    def test_list_queries(self, client: TestClient):
        """Test GET /projects/{id}/queries returns project's queries."""
        project = client.post("/projects/", json={"name": "Test"}).json()

        client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "Query 1"},
        )
        client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "Query 2"},
        )

        response = client.get(f"/projects/{project['id']}/queries")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_query(self, client: TestClient):
        """Test GET /queries/{id} returns specific query."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        query = client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "My question"},
        ).json()

        response = client.get(f"/queries/{query['id']}")
        assert response.status_code == 200
        assert response.json()["queryText"] == "My question"

    def test_update_query(self, client: TestClient):
        """Test PATCH /queries/{id} updates query (adds AI response)."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        query = client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "My question"},
        ).json()

        response = client.patch(
            f"/queries/{query['id']}",
            json={
                "responseText": "AI generated answer",
                "tokensUsed": 500,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["responseText"] == "AI generated answer"
        assert data["tokensUsed"] == 500


class TestCascadeDeletes:
    """Test cascade delete behavior."""

    def test_delete_project_cascades_to_files(self, client: TestClient):
        """Deleting project also deletes files."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "test.pdf", "fileType": "pdf"},
        ).json()

        # Delete project
        client.delete(f"/projects/{project['id']}")

        # File should be gone
        response = client.get(f"/files/{file['id']}")
        assert response.status_code == 404

    def test_delete_file_cascades_to_pointers(self, client: TestClient):
        """Deleting file also deletes pointers."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        file = client.post(
            f"/projects/{project['id']}/files",
            json={"name": "test.pdf", "fileType": "pdf"},
        ).json()
        pointer = client.post(
            f"/files/{file['id']}/pointers",
            json={
                "pageNumber": 1,
                "bounds": {"xNorm": 0.1, "yNorm": 0.2, "wNorm": 0.3, "hNorm": 0.4},
            },
        ).json()

        # Delete file
        client.delete(f"/files/{file['id']}")

        # Pointer should be gone
        response = client.get(f"/pointers/{pointer['id']}")
        assert response.status_code == 404

    def test_delete_project_cascades_to_queries(self, client: TestClient):
        """Deleting project also deletes queries."""
        project = client.post("/projects/", json={"name": "Test"}).json()
        query = client.post(
            f"/projects/{project['id']}/queries",
            json={"queryText": "Test query"},
        ).json()

        # Delete project
        client.delete(f"/projects/{project['id']}")

        # Query should be gone
        response = client.get(f"/queries/{query['id']}")
        assert response.status_code == 404
