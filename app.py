import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv

from extensions import limiter, csrf
from storage import _load_json, UPLOAD_FOLDER
from api import api as api_blueprint

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY']             = os.getenv("APP_KEY")
app.config['SESSION_PERMANENT']      = False   # session cookie — expires when browser closes
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_TYPE']           = "filesystem"
app.config['UPLOAD_FOLDER']          = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH']     = 5 * 1024 * 1024  # 5 MB

# ── Extensions ────────────────────────────────────────────────────────────────
csrf.init_app(app)
limiter.init_app(app)

# Register the API blueprint and exempt it from CSRF so mobile clients
# (which don't have a CSRF cookie) can call the same endpoints later.
# Web clients already include X-CSRFToken on every fetch() call.
app.register_blueprint(api_blueprint)
csrf.exempt(api_blueprint)

# ── Auth guards (page routes only) ────────────────────────────────────────────
def _producer_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (session.get('logged_in') and session.get('user_type') == 'producer'):
            return redirect(url_for('producer_login'))
        return f(*args, **kwargs)
    return decorated

def _customer_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (session.get('logged_in') and session.get('user_type') == 'customer'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def _admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (session.get('logged_in') and session.get('username') == 'admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Security headers ──────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options']        = 'SAMEORIGIN'
    response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']     = 'geolocation=(), camera=(), microphone=()'
    return response

# ── Session setup ─────────────────────────────────────────────────────────────
@app.before_request
def setup():
    if 'logged_in' not in session:
        session['logged_in'] = False

@app.context_processor
def inject_globals():
    return {
        'username':  session.get('username', ''),
        'logged_in': session.get('logged_in', False),
    }

# ── Error handlers ─────────────────────────────────────────────────────────────
from flask_wtf.csrf import CSRFError

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return {"error": "CSRF token missing or invalid", "message": e.description}, 400

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "File is too large (max 5MB)"}), 413

@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({"status": "error", "message": "Too many attempts. Please wait before trying again."}), 429

# ── Page routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/login')
def login():
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/customer_register')
def customer_register():
    return render_template("register.html")

@app.route('/account')
@_customer_required
def customer_account():
    return render_template("account.html")

@app.route('/producer_login')
def producer_login():
    return render_template("producer_login.html")

@app.route('/producer_registration')
def producer_registration():
    return render_template("producer_registration.html")

@app.route('/producer_onboarding')
def producer_onboarding():
    return render_template("producer_onboarding.html")

@app.route('/producer_dashboard')
@_producer_required
def producer_dashboard():
    return render_template("producer_dashboard.html")

@app.route('/producer_landing/<producer_id>')
def producer_landing(producer_id):
    return render_template('producer_landing.html', producer_id=producer_id)

# ── Product & producer browse pages ──────────────────────────────────────────

@app.route('/products')
def products():
    return render_template('products.html')

@app.route('/producers')
def producers():
    return render_template('producers.html')

@app.route('/producers/<username>')
def producer_profile(username):
    return render_template('producer_profile.html', username=username)

@app.route('/markets')
def markets():
    return render_template('markets.html')

@app.route('/admin')
@_admin_required
def admin():
    return render_template('admin.html')

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=5000)
