"""
storage.py – thin JSON file-storage helpers shared across app.py and api.py.
"""

import os
import json

UPLOAD_FOLDER = "static"


def _load_json(filename: str, default=None):
    """Load a JSON file from the static folder, returning default on error."""
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return default if default is not None else []
    with open(path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default if default is not None else []


def _save_json(filename: str, data) -> None:
    path = os.path.join(UPLOAD_FOLDER, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
