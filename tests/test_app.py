from unittest.mock import patch


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

    # We need to provide the fields defined in your ItemForm
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
