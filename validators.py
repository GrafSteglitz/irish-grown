"""
@module
"""
import os
from dotenv import dotenv_values
from werkzeug.security import check_password_hash
import re

def validate_password(password: str):
    # 1. Regex check for complexity and length (8-30 characters)
    complexity_pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,30}$"

    # 2. Blacklist for common patterns/words
    blacklist = [
        "12345", "54321", "123456", "abcdef", "qwerty", "password",
        "admin", "welcome", "p@ssword", "letmein"
    ]

    # Check for complexity first
    if not re.match(complexity_pattern, password):
        errors = []
        if len(password) < 8: errors.append("Minimum 8 characters")
        if len(password) > 30: errors.append("Maximum 30 characters")
        if not re.search(r"[A-Z]", password): errors.append("Uppercase letter")
        if not re.search(r"[a-z]", password): errors.append("Lowercase letter")
        if not re.search(r"\d", password): errors.append("Digit")
        if not re.search(r"[!@#$%^&*]", password): errors.append("Special character")
        return False, f"Complexity failed: {', '.join(errors)}"

    # Check against blacklist (case-insensitive)
    pw_lower = password.lower()
    for forbidden in blacklist:
        if forbidden in pw_lower:
            return False, f"Security risk: Contains forbidden sequence '{forbidden}'"

    return True, "Password is valid and secure."

def validate_username(username: str):
    if len(username) > 30:
        return False, "Username too long"
    db = []
    # TODO: Connect to the db and check for existing usernames
    if username in db:
        return False, "Username already taken"
    return True, "Username ok"

def check_password(username, plain_password):
    """Verify a login attempt against .test_logins.
    Supports both legacy plaintext entries and entries hashed with werkzeug."""
    logins_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.test_logins')
    config = dotenv_values(logins_path)
    stored = config.get(username)
    if stored is None:
        return False
    # Hashed entries start with the algorithm prefix (e.g. "pbkdf2:sha256:")
    if stored.startswith('pbkdf2:') or stored.startswith('scrypt:'):
        return check_password_hash(stored, plain_password)
    # Legacy plaintext comparison (existing accounts before hashing was added)
    return stored == plain_password