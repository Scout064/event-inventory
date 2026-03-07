import sys
import site

# Add project path
sys.path.insert(0, '/var/www/inventory')

# Add virtual environment site-packages
site.addsitedir('/var/www/inventory/inventory_app/venv/lib/python3.11/site-packages')

# Import your Flask app
from inventory_app.app import app as application  # noqa: E402, F401
