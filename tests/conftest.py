import pytest
from unittest.mock import patch, MagicMock
from inventory_app.app import app as flask_app
from inventory_app.app import User
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test_secret"
    })
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Fixture that mocks an active admin session."""
    admin_user = User(
        id=1,
        username="admin",
        password_hash=generate_password_hash("password"),
        is_admin=True
    )
    with patch("flask_login.utils._get_user", return_value=admin_user):
        yield client


@pytest.fixture
def mock_db():
    """Fixture to provide a pre-configured database mock."""
    with patch("inventory_app.app.get_db") as mocked_get_db:
        mock_conn = MagicMock()
        mocked_get_db.return_value = mock_conn
        yield mock_conn
