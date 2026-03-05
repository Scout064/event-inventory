from unittest.mock import patch
import io


@patch("inventory_app.app.load_config")
def test_list_items(mock_load, authenticated_client, mock_db):
    """Tests GET /items with a pre-logged in user."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.return_value = [
        ("ID1", "Mic", "Audio", "SN1", "Shure", "SM58")
    ]
    response = authenticated_client.get("/items")
    assert response.status_code == 200
    assert b"Shure" in response.data


@patch("inventory_app.app.load_config")
def test_add_item(mock_load, authenticated_client, mock_db):
    """Tests POST /items/new."""
    mock_load.return_value = {"configured": True}
    response = authenticated_client.post(
        "/items/new",
        data={
            "inventory_id": "ACC-001",
            "name": "New Item",
            "category": "Video",
            "description": "A test camera",
            "serial_number": "X1",
            "manufacturer": "Sony",
            "model": "A7S"
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Item created." in response.data


@patch("inventory_app.app.load_config")
def test_item_label_png(mock_load, authenticated_client, mock_db):
    """Tests GET /labels/<id>.png generation."""
    mock_load.return_value = {"configured": True, "logo_path": None}
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchone.return_value = (
        "ACC-001", "Mic", "Audio", "SN123", "Shure", "SM58"
    )
    response = authenticated_client.get("/labels/ACC-001.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert len(response.data) > 0


@patch("inventory_app.app.load_config")
def test_inventory_pdf_report(mock_load, authenticated_client, mock_db):
    """Tests GET /reports/items.pdf."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.return_value = [
        ("ID1", "Item A", "Cat1", "SN-A", "MakeA", "ModA")
    ]
    response = authenticated_client.get("/reports/items.pdf")
    assert response.status_code == 200
    assert b"%PDF" in response.data


@patch("inventory_app.app.load_config")
def test_search_logic_integrity(mock_load, authenticated_client, mock_db):
    """Verifies multi-category search returns correct data."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.side_effect = [
        [("ITM-01", "MacBook Pro", "IT", "Apple")],
        [(50, "Annual Meeting", "2026-12-01")],
        [(3, "admin_user", 1)]
    ]
    response = authenticated_client.get("/search?q=MacBook")
    assert response.status_code == 200
    assert b"MacBook Pro" in response.data
    assert b"Annual Meeting" in response.data


@patch("inventory_app.app.load_config")
def test_admin_view_user_list(mock_load, authenticated_client, mock_db):
    """Tests that an Admin can view the user management page."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Matches SELECT id, username, is_admin FROM users
    mock_cur.fetchall.return_value = [
        (1, "admin", 1),
        (2, "tech_user", 0)
    ]
    response = authenticated_client.get("/admin/users")
    assert response.status_code == 200
    assert b"User Management" in response.data
    assert b"tech_user" in response.data


@patch("inventory_app.app.load_config")
def test_admin_add_user_success(mock_load, authenticated_client, mock_db):
    """Tests the Admin's ability to create a new user."""
    mock_load.return_value = {"configured": True}
    response = authenticated_client.post(
        "/admin/users/new",
        data={
            "username": "stage_hand",
            "password": "securepassword",
            "is_admin": "y"  # BooleanField expects 'y' or checkbox value
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    # Updated to match app.py line 757
    assert b"User created." in response.data
    mock_cur = mock_db.cursor.return_value
    mock_cur.execute.assert_called()


@patch("inventory_app.app.load_config")
def test_admin_delete_other_user(mock_load, authenticated_client, mock_db):
    """Tests deleting a different user (ID 2)."""
    mock_load.return_value = {"configured": True}
    response = authenticated_client.post("/admin/users/2/delete", follow_redirects=True)
    assert response.status_code == 200
    # Matches app.py line 778
    assert b"User deleted successfully." in response.data
    mock_cur = mock_db.cursor.return_value
    mock_cur.execute.assert_any_call("DELETE FROM users WHERE id=%s", (2,))


@patch("inventory_app.app.load_config")
def test_admin_delete_self_safety_check(mock_load, authenticated_client, mock_db):
    """Verifies the safety check: Admin cannot delete themselves."""
    mock_load.return_value = {"configured": True}
    # User ID 1 is the admin in the authenticated_client fixture
    response = authenticated_client.post("/admin/users/1/delete", follow_redirects=True)
    assert response.status_code == 200
    # Matches app.py line 769
    assert b"You cannot delete your own admin account." in response.data
    mock_cur = mock_db.cursor.return_value
    for call in mock_cur.execute.call_args_list:
        assert not (call[0][0].startswith("DELETE FROM users") and call[0][1] == (1,))


@patch("inventory_app.app.load_config")
def test_items_download_template(mock_load, authenticated_client):
    """Verifies the CSV template generation and headers."""
    mock_load.return_value = {"configured": True}
    response = authenticated_client.get("/items/template")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    # Verify the headers we defined in app.py are present
    assert b"inventory_id,name,category,description,serial_number,manufacturer,model" in response.data
    # Verify the example row is present
    assert b"MIC-001,SM58" in response.data


@patch("inventory_app.app.load_config")
def test_items_bulk_import_logic(mock_load, authenticated_client, mock_db):
    """Tests the CSV import processing and DB execution."""
    mock_load.return_value = {"configured": True}
    # Create a dummy CSV file in memory
    csv_content = (
        "inventory_id,name,category,description,serial_number,manufacturer,model\r\n"
        "TEST-01,Bulk Item,Audio,Testing description,SN-BULK,BrandX,ModY\r\n"
    )
    data = {
        'csv_file': (io.BytesIO(csv_content.encode('utf-8')), 'test_import.csv')
    }
    response = authenticated_client.post(
        "/items/import",
        data=data,
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Import complete!" in response.data
    # Verify the database was actually called with the correct data
    mock_cur = mock_db.cursor.return_value
    # Check if the execute was called with our "ON DUPLICATE KEY UPDATE" query
    calls = mock_cur.execute.call_args_list
    found_import_call = any("INSERT INTO items" in str(call) for call in calls)
    assert found_import_call is True
