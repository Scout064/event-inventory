# wsgi.py
# In Docker, packages are installed system-wide by the Dockerfile.
# No venv path manipulation needed — gunicorn finds everything on sys.path already.
from inventory_app.app import create_app
application = create_app()
