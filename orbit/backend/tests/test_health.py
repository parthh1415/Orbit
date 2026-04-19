"""Smoke test for ORBIT backend."""


def test_app_imports() -> None:
    """Verify the FastAPI app can be imported."""
    from app.main import app

    assert app.title == "ORBIT"
