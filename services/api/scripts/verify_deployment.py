#!/usr/bin/env python3
"""Run after deployment to verify everything works."""

import sys

import httpx

API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def check_health():
    """Verify health endpoint returns 200."""
    r = httpx.get(f"{API_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    data = r.json()
    assert data.get("status") == "healthy", f"Unexpected health response: {data}"
    print("✓ Health check passed")


def check_auth_required():
    """Verify protected routes require authentication."""
    r = httpx.get(f"{API_URL}/projects/")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    print("✓ Auth required for protected routes")


def check_docs():
    """Verify API docs are accessible."""
    r = httpx.get(f"{API_URL}/docs")
    assert r.status_code == 200, f"Docs not accessible: {r.status_code}"
    print("✓ API docs accessible")


def check_openapi():
    """Verify OpenAPI schema is accessible."""
    r = httpx.get(f"{API_URL}/openapi.json")
    assert r.status_code == 200, f"OpenAPI schema not accessible: {r.status_code}"
    data = r.json()
    assert "paths" in data, "OpenAPI schema missing paths"
    print("✓ OpenAPI schema accessible")


if __name__ == "__main__":
    print(f"\nVerifying deployment at: {API_URL}\n")

    try:
        check_health()
        check_auth_required()
        check_docs()
        check_openapi()
        print("\n✅ All checks passed!\n")
    except AssertionError as e:
        print(f"\n❌ Check failed: {e}\n")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"\n❌ Could not connect to {API_URL}\n")
        sys.exit(1)
