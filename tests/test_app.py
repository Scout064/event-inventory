from unittest.mock import patch
import io

@patch("inventory_app.app.load_config")
def test_list_items(mock_load, authenticated_client, mock_db):
    """Tests GET /items with a pre-logged in user."""
    mock_load.return_value = {"configured": True}

    # Setup mock data (must match the SELECT order in app.py)
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.return_value = [
        ("ID1", "Mic", "Audio", "SN1", "Shure", "SM58")
    ]

    # Action
    response = authenticated_client.get("/items")

    # Assert
    assert response.status_code == 200
    assert b"Shure" in response.data


@patch("inventory_app.app.load_config")
def test_add_item(mock_load, authenticated_client, mock_db):
    """Tests POST /items/new (the correct route)."""
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

    # Assert 200 because follow_redirects takes us to the items list
    assert response.status_code == 200
    assert b"Item created." in response.data


@patch("inventory_app.app.load_config")
def test_item_label_png(mock_load, authenticated_client, mock_db):
    """Tests GET /labels/<id>.png generation with QR and Logo."""
    mock_load.return_value = {"configured": True, "logo_path": None}
    
    # Mock DB to return one item
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchone.return_value = (
        "ACC-001", "Mic", "Audio", "SN123", "Shure", "SM58"
    )

    response = authenticated_client.get("/labels/ACC-001.png")
    
    # Assertions
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    # Verify we actually got image data back
    assert len(response.data) > 0


@patch("inventory_app.app.load_config")
def test_inventory_pdf_report(mock_load, authenticated_client, mock_db):
    """Tests GET /reports/items.pdf for the full inventory."""
    mock_load.return_value = {"configured": True}
    
    # Mock DB for the SELECT query in report_items_pdf
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.return_value = [
        ("ID1", "Item A", "Cat1", "SN-A", "MakeA", "ModA"),
        ("ID2", "Item B", "Cat2", "SN-B", "MakeB", "ModB")
    ]

    response = authenticated_client.get("/reports/items.pdf")
    
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert b"%PDF" in response.data  # PDF files always start with this header


@patch("inventory_app.app.load_config")
def test_production_bom_pdf(mock_load, authenticated_client, mock_db):
    """Tests GET /reports/production/<id>.pdf for a specific show."""
    mock_load.return_value = {"configured": True}
    
    mock_cur = mock_db.cursor.return_value
    # 1. First fetch is for the Production details
    mock_cur.fetchone.return_value = (1, "Gala 2024", None, "Test Notes")
    # 2. Second fetch is for the assigned Items (BOM)
    mock_cur.fetchall.return_value = [
        ("ID1", "Speaker", "Audio", "SN99", "d&b", "Q7")
    ]

    response = authenticated_client.get("/reports/production/1.pdf")
    
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.headers["Content-Disposition"].startswith("attachment")
