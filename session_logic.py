from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, url_for

# 1. Define the blueprint
# 'users' is the internal name, __name__ helps locate resources
user_bp = Blueprint('session_logic', __name__)

@user_bp.route('/verify', methods=['POST'])
def check_login():
    if not request:
        return jsonify({"status": "error", "message": "No request data"})
    data = request.get_json()
    if not data["username"]:
        return jsonify({"status": "error", "message": "Empty username"})
    if not data["password"]:
        return jsonify({"status": "error", "message": "Empty password"})
    return jsonify({"status": "success","message":"Successful login"})

def producer_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('type', '') != 'producer' or 'username' not in session:  # Or your own session key
            return redirect(url_for('producer_login'))  # Redirect to login page
        return f(*args, **kwargs)
    return decorated_function

def post(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # We add the extra argument here
        kwargs['methods'] = ['POST']
        # Then pass everything to the function
        return f(*args, **kwargs)
    return wrapper



