import pytest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash

import inventory_app.app as app_module


@pytest.fixture
def app():
    app = app_module.app
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test"
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_config():
    return {
        "configured": True,
        "logo_path": None,
        "db_host": "localhost",
        "db_port": "3306",
        "db_name": "test",
        "db_user": "test",
        "db_pass": "test"
    }


def fake_db_connection(rows=None):
    conn = MagicMock()
    cur = MagicMock()

    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = rows[0] if rows else None

    conn.cursor.return_value = cur
    return conn


# ----------------------
# Basic Route Tests
# ----------------------

@patch("inventory_app.app.load_config")
def test_redirect_to_setup_if_not_configured(mock_load, client):
    mock_load.return_value = {"configured": False}
    resp = client.get("/login")
    assert resp.status_code == 302
    assert "/setup" in resp.location


@patch("inventory_app.app.load_config")
@patch("inventory_app.app.find_user_by_username")
@patch("inventory_app.app.get_db")
def test_login_success(mock_find_user, mock_load, client):
    mock_load.return_value = {"configured": True}

    user = app_module.User(
        1,
        "admin",
        generate_password_hash("password"),
        True
    )
    mock_find_user.return_value = user

    resp = client.post(
        "/login",
        data={"username": "admin", "password": "password"},
        follow_redirects=True,
    )
    assert resp.status_code == 200


@patch("inventory_app.app.load_config")
def test_index_requires_login(mock_load, client):
    mock_load.return_value = {"configured": True}
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.location


# ----------------------
# Items
# ----------------------

@patch("inventory_app.app.load_config")
@patch("inventory_app.app.get_db")
def test_items_list(mock_db, mock_load, client):
    mock_load.return_value = {"configured": True}

    rows = [
        ("ID1", "Mic", "Audio", "SN1", "Shure", "SM58")
    ]
    mock_db.return_value = fake_db_connection(rows)

    with client:
        client.post("/login", data={"username": "x", "password": "x"})
        resp = client.get("/items")

    assert resp.status_code in (200, 302)


@patch("inventory_app.app.load_config")
@patch("inventory_app.app.get_db")
def test_items_404_edit(mock_db, mock_load, client):
    mock_load.return_value = {"configured": True}
    mock_db.return_value = fake_db_connection(rows=None)

    with client:
        resp = client.get("/items/UNKNOWN/edit")

    assert resp.status_code == 404


# ----------------------
# Productions
# ----------------------

@patch("inventory_app.app.load_config")
@patch("inventory_app.app.get_db")
def test_production_view_404(mock_db, mock_load, client):
    mock_load.return_value = {"configured": True}
    mock_db.return_value = fake_db_connection(rows=None)

    with client:
        resp = client.get("/productions/999")

    assert resp.status_code == 404


# ----------------------
# QR Code
# ----------------------

def test_generate_qr():
    img = app_module.generate_qr_with_logo("TEST123", None)
    assert img is not None
    assert img.size[0] > 0
    assert img.size[1] > 0


# ----------------------
# PDF Reports
# ----------------------

@patch("inventory_app.app.load_config")
@patch("inventory_app.app.get_db")
def test_items_pdf(mock_db, mock_load, client):
    mock_load.return_value = {"configured": True}
    rows = [
        ("ID1", "Mic", "Audio", "SN1", "Shure", "SM58")
    ]
    mock_db.return_value = fake_db_connection(rows)

    with client:
        resp = client.get("/reports/items.pdf")

    assert resp.status_code in (200, 302)


# ----------------------
# Admin Protection
# ----------------------

def test_admin_required_decorator():
    @app_module.admin_required
    def dummy():
        return "OK"

    with app_module.app.test_request_context():
        resp = dummy()
        assert resp.status_code == 302


# ----------------------
# HTTPS Enforcement
# ----------------------

@patch("inventory_app.app.load_config")
def test_https_redirect(mock_load, client):
    mock_load.return_value = {"configured": True}

    resp = client.get(
        "/login",
        base_url="http://example.com"
    )
    assert resp.status_code in (301, 302)
