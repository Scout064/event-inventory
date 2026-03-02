from unittest.mock import patch


@patch("inventory_app.app.load_config")
def test_list_items(mock_load, authenticated_client, mock_db):
    """Tests GET /items with a pre-logged in user."""
    mock_load.return_value = {"configured": True}

    # Setup mock data
    mock_cur = mock_db.cursor.return_value
    mock_cur.fetchall.return_value = [
        (1, "Mic", "Audio", "SN1", "Shure", "SM58")
    ]

    # Action
    response = authenticated_client.get("/items")

    # Assert
    assert response.status_code == 200
    assert b"Shure" in response.data


@patch("inventory_app.app.load_config")
def test_add_item(mock_load, authenticated_client, mock_db):
    """Tests POST /add."""
    mock_load.return_value = {"configured": True}

    response = authenticated_client.post(
        "/add",
        data={
            "name": "New Item",
            "category": "Video",
            "serial": "X1",
            "make": "Sony",
            "model": "A7S"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Item added successfully" in response.data
