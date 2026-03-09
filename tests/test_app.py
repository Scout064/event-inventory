from unittest.mock import patch
import io
import datetime
from werkzeug.security import generate_password_hash
from datetime import date


@patch("inventory_app.app.load_config")
def test_list_items(mock_load, authenticated_client, mock_db):
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # First call: COUNT(*) fetchone()
    # Second call: rows fetchall()
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.return_value = [
        ("ID1", "Mic", "Audio", "SN1", "Shure", "SM58")
    ]
    response = authenticated_client.get("/items")
    assert response.status_code == 200
    assert b"Shure" in response.data
    # VERIFICATION CHANGED: Check the header count instead of hidden pagination
    assert b"Items (1)" in response.data


@patch("inventory_app.app.load_config")
def test_add_item(mock_load, authenticated_client, mock_db):
    """Tests POST /items/new."""
    mock_load.return_value = {"configured": True}
    # NEW: Mock the DB responses for the redirect to /items
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchone.return_value = (1,)  # total_items = 1
    mock_cur.fetchall.return_value = []   # empty list of items
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
    # Since total_items was 1, verify the header we added earlier
    assert b"Items (1)" in response.data


@patch("inventory_app.app.load_config")
def test_edit_item_id_readonly(mock_load, authenticated_client, mock_db):
    """Verifies that the inventory_id is marked as readonly on the edit page."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Mock finding the item to edit
    mock_cur.fetchone.return_value = ("ACC-001", "Mic", "Audio", "Desc", "SN1", "Man", "Mod")

    response = authenticated_client.get("/items/ACC-001/edit")
    assert response.status_code == 200
    # Check if the readonly attribute is rendered in the HTML for the ID field
    assert b'readonly' in response.data
    assert b'ACC-001' in response.data


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
def test_items_search_query(mock_load, authenticated_client, mock_db):
    """Verifies that the search query 'q' is passed to the SQL query with wildcards."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Mock return values for pagination and results
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.return_value = [("ID1", "SearchTarget", "Cat", "SN", "Man", "Mod")]

    response = authenticated_client.get("/items?q=SearchTarget")
    assert response.status_code == 200

    # FIX: Instead of checking the very last call (which is now the branding query),
    # we search through the history of calls (call_args_list)
    search_executed = False
    for call in mock_cur.execute.call_args_list:
        # call[0] is the tuple of positional arguments: (sql_string, params_tuple)
        args = call[0]
        if len(args) > 1 and "%SearchTarget%" in str(args[1]):
            search_executed = True
            break

    assert search_executed, "The search SQL with wildcards was never executed."


@patch("inventory_app.app.load_config")
@patch("inventory_app.app.get_item_suggestions")
def test_item_form_datalist_suggestions(mock_suggestions, mock_load, authenticated_client):
    """
    Verifies that 'New Item' page fetches distinct values for
    Category, Manufacturer, and Model to populate datalists.
    """
    mock_load.return_value = {"configured": True}
    mock_suggestions.return_value = {
        "category": ["Audio", "Video"],
        "manufacturer": ["Sony", "Shure"],
        "model": ["SM58", "A7S"]
    }

    response = authenticated_client.get("/items/new")
    assert response.status_code == 200

    # Check datalist structure
    assert b'id="category_list"' in response.data
    assert b'id="manufacturer_list"' in response.data
    assert b'id="model_list"' in response.data

    # Check specific suggestion values
    assert b'value="Audio"' in response.data
    assert b'value="Sony"' in response.data
    assert b'value="SM58"' in response.data


@patch("inventory_app.app.load_config")
def test_edit_item_includes_suggestions(mock_load, authenticated_client, mock_db):
    """
    Verifies that the 'Edit Item' page also provides autocomplete suggestions.
    """
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # 1. First fetchone() for the item itself
    mock_cur.fetchone.return_value = ("ACC-01", "Cam", "Video", "Desc", "SN1", "Sony", "A7")
    # 2. Subsequent fetchall() calls for the three suggestion lists
    mock_cur.fetchall.side_effect = [
        [("Audio",), ("Video",)],
        [("Sony",)],
        [("A7",)]
    ]
    response = authenticated_client.get("/items/ACC-01/edit")
    assert response.status_code == 200
    # Verify the current item data is there
    assert b"ACC-01" in response.data
    # Verify the suggestions are also present in the HTML
    assert b'id="category_list"' in response.data
    assert b'value="Video"' in response.data


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
def test_production_pdf_report_with_notes(mock_load, authenticated_client, mock_db):
    """Tests the BOM PDF generation including the text wrap logic for long notes."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value

    # Mock production header (id, name, date, notes)
    long_note = "A" * 150  # Create a long note to trigger wrapping
    mock_cur.fetchone.return_value = (1, "Summer Festival", "2026-07-15", long_note)

    # Mock items assigned to production
    mock_cur.fetchall.return_value = [
        ("ID1", "Item A", "Cat1", "SN-A", "MakeA", "ModA")
    ]

    response = authenticated_client.get("/reports/production/1.pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
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
def test_user_profile_update_success(mock_load, authenticated_client, mock_db):
    """Tests that a user can update their profile with matching passwords and correct current password."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Mock the DB response for the profile route's SELECT query
    # Matches: username, real_name, email, birthday, password_hash
    mock_cur.fetchone.return_value = (
        "admin", "Admin User", "admin@example.com", date(1990, 1, 1),
        generate_password_hash("oldpassword123")
    )
    response = authenticated_client.post(
        "/profile",
        data={
            "username": "admin",
            "real_name": "Admin User",
            "email": "admin@example.com",
            "birthday": "1990-01-01",
            "current_password": "oldpassword123",  # Satisfies the new security requirement
            "password": "newpassword123",
            "confirm_password": "newpassword123",
            "submit": "Save Profile"
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Profile updated successfully." in response.data


@patch("inventory_app.app.load_config")
def test_user_profile_update_wrong_current_password(mock_load, authenticated_client, mock_db):
    """Tests that a password update fails if the current password is wrong."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Mock the DB response with a known hash
    mock_cur.fetchone.return_value = (
        "admin", "Admin User", "admin@example.com", "1990-01-01",
        generate_password_hash("actualpassword123")
    )
    response = authenticated_client.post(
        "/profile",
        data={
            "username": "admin",
            "current_password": "WRONGpassword999",  # Wrong password!
            "password": "newpassword123",
            "confirm_password": "newpassword123",
            "submit": "Save Profile"
        },
        follow_redirects=True
    )
    # Verify the form caught the error
    assert b"Current Password is required and must be correct" in response.data


@patch("inventory_app.app.load_config")
def test_profile_update_confirm_required(mock_load, authenticated_client, mock_db):
    mock_load.return_value = {"configured": True}
    # Deliberately mismatch the passwords
    response = authenticated_client.post("/profile", data={
        "username": "ValidUser",
        "password": "newpassword123",
        "confirm_password": "wrongpassword456",  # Mismatch!
        "submit": "Save Profile"
    })
    # Verify the form caught the error
    assert b"Passwords must match" in response.data


@patch("inventory_app.app.load_config")
def test_username_validation_rules(mock_load, authenticated_client, mock_db):
    mock_load.return_value = {"configured": True}
    # 1. Test invalid special characters
    response = authenticated_client.post("/profile", data={
        "username": "User<Script>",  # Forbidden characters
        "submit": "Save Profile"
    })
    assert b"Username contains invalid special characters" in response.data
    # 2. Test length limit (33 chars)
    long_username = "A" * 33
    response = authenticated_client.post("/profile", data={
        "username": long_username,
        "submit": "Save Profile"
    })
    assert b"Username must be between 3 and 32 characters" in response.data
    # 3. Test allowed language-specific characters (Should PASS)
    response = authenticated_client.post("/profile", data={
        "username": "Müller_éè",
        "submit": "Save Profile"
    })
    # If the regex works, it won't show the error message
    assert b"Username contains invalid special characters" not in response.data


@patch("inventory_app.app.load_config")
def test_admin_add_user_success(mock_load, authenticated_client, mock_db):
    """Tests the Admin's ability to create a new user with password confirmation."""
    mock_load.return_value = {"configured": True}
    response = authenticated_client.post(
        "/admin/users/new",
        data={
            "username": "stage_hand",
            "password": "securepassword",
            "confirm_password": "securepassword",
            "is_admin": "y"
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"User created." in response.data


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
    # NEW: Mock DB responses for the redirect to /items
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchone.return_value = (1,)
    mock_cur.fetchall.return_value = []
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
    assert b"1 Items Imported, 0 not Imported (identical ID)" in response.data


@patch("inventory_app.app.load_config")
def test_production_validation_rules(mock_load, authenticated_client, mock_db):
    """Tests that the Production form enforces the 32-char name and 255-char notes limits."""
    mock_load.return_value = {"configured": True}
    # 1. Test Name too long (33 characters)
    long_name = "A" * 33
    response = authenticated_client.post("/productions/new", data={
        "name": long_name,
        "date": "2026-03-07",
        "notes": "Valid notes",
        "submit": "Save"
    })
    # WTForms should reject this and return the form with the error message
    assert b"Name must be between 1 and 32 characters" in response.data
    # 2. Test Notes too long (256 characters)
    long_notes = "A" * 256
    response = authenticated_client.post("/productions/new", data={
        "name": "Valid Name",
        "date": "2026-03-07",
        "notes": long_notes,
        "submit": "Save"
    })
    # WTForms should reject this and return the form with the error message
    assert b"Notes cannot exceed 255 characters" in response.data


@patch("inventory_app.app.load_config")
def test_add_production_success(mock_load, authenticated_client, mock_db):
    """Tests successful creation of a new Production."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value
    # Mock the response for the redirect to /productions list page
    mock_cur.fetchall.return_value = [
        (1, "Summer Festival", "2026-07-15", "Outdoor event notes")
    ]
    response = authenticated_client.post(
        "/productions/new",
        data={
            "name": "Summer Festival",
            "date": "2026-07-15",
            "notes": "Outdoor event notes",
            "submit": "Save"
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    # Verify the flash message from app.py
    assert b"Production created." in response.data
    # Verify the database execution was called with the correctly parsed date
    expected_date = datetime.date(2026, 7, 15)
    # Iterate through database calls to find our INSERT statement
    insert_called = False
    for call in mock_cur.execute.call_args_list:
        query = call[0][0]
        if "INSERT INTO productions" in query:
            insert_called = True
            args = call[0][1]
            assert args[0] == "Summer Festival"
            assert args[1] == expected_date
            assert args[2] == "Outdoor event notes"
    assert insert_called


@patch("inventory_app.app.load_config")
def test_productions_search(mock_load, authenticated_client, mock_db):
    """Verifies that the productions list can be searched by name."""
    mock_load.return_value = {"configured": True}
    mock_cur = mock_db.cursor.return_value

    mock_cur.fetchall.return_value = [
        (1, "Target Festival", "2026-07-15", "Notes")
    ]

    response = authenticated_client.get("/productions?q=Target")
    assert response.status_code == 200
    assert b"Target Festival" in response.data

    # Check if our SQL was called with the search term and wildcards
    search_executed = False
    for call in mock_cur.execute.call_args_list:
        args = call[0]
        if len(args) > 1 and "%Target%" in str(args[1]):
            search_executed = True
            break

    assert search_executed, "The productions search SQL was never executed."
