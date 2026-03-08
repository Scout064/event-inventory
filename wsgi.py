import sys
import os
import glob

# Base path to your virtual environment
venv_base = '/var/www/inventory/inventory_app/venv'

# Dynamically find the site-packages path
# This looks for 'lib/python*/site-packages' and picks the first one it finds
try:
    pattern = os.path.join(venv_base, 'lib', 'python*', 'site-packages')
    venv_site_packages = glob.glob(pattern)[0]

    if venv_site_packages not in sys.path:
        sys.path.insert(0, venv_site_packages)
except IndexError:
    # Fallback or error logging if no venv is found
    print("Warning: Could not dynamically find virtual environment site-packages.")

# Add the application directory
sys.path.insert(0, '/var/www/inventory')

from inventory_app.app import app as application  # noqa: E402, F401
