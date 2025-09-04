import sys
import site  # <--- This is required

# Add project path
sys.path.insert(0, '/var/www/inventory')

# Add virtual environment site-packages
site.addsitedir('/var/www/inventory/venv/lib/python3.11/site-packages')

# Import your Flask app
from app import app as application
