"""
extensions.py – shared Flask extension instances.

Import these in both app.py and api.py to avoid circular imports.
Call .init_app(app) in the application factory (app.py).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

limiter = Limiter(
    get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)

csrf = CSRFProtect()
