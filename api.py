"""
api.py – REST API blueprint for Irish Grown.

All routes are mounted under /api (registered in app.py).

Route map
---------
Auth
  POST  /api/auth/customer/login
  POST  /api/auth/customer/register
  POST  /api/auth/producer/login
  POST  /api/auth/producer/onboarding/account
  POST  /api/auth/producer/onboarding/complete
  POST  /api/auth/logout
  GET   /api/auth/me                (current session info)

Cart
  GET   /api/cart/contents
  POST  /api/cart/add
  POST  /api/cart/remove
  POST  /api/cart/update

Checkout
  POST  /api/checkout/submit

Coupons
  GET   /api/coupons
  POST  /api/coupons/create
  POST  /api/coupons/delete
  GET   /api/coupons/validate

Products
  POST  /api/products/add
  POST  /api/products/update-stock
  GET   /api/search

Producer settings
  GET   /api/producer/settings
  POST  /api/producer/settings
  GET   /api/producer/pickup-locations
  POST  /api/producer/product-delivery

Design notes
------------
- Session-based auth (cookie) is used for web clients – the same Flask session
  cookie issued by the main app is accepted here.
- This blueprint is CSRF-exempt (see app.py: csrf.exempt(api)).  Web clients
  already include the X-CSRFToken header on every fetch() call; future mobile
  clients will authenticate with Bearer tokens instead (not yet implemented).
- All responses are JSON.  Login/register routes return a `redirect` field that
  the calling JavaScript should honour with window.location.href.
"""

import os
import json
import re
from datetime import datetime, date
from functools import wraps

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from extensions import limiter
from storage import _load_json, _save_json, UPLOAD_FOLDER
from validators import validate_password, validate_username, check_password

# ── Blueprint ─────────────────────────────────────────────────────────────────

api = Blueprint("api", __name__, url_prefix="/api")

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_MIMES      = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_UPLOAD_BYTES   = 5 * 1024 * 1024

DELIVERY_FEES = {
    "collect_in_person": 0.0,
    "market_pickup":     0.0,
    "dropoff_box":       0.0,
    "producer_delivery": 3.99,
}

# ── Auth decorators ───────────────────────────────────────────────────────────

def _require_login(f):
    """Any authenticated session (customer or producer)."""
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"status": "error", "message": "Login required"}), 401
        return f(*args, **kwargs)
    return _wrap


def _require_producer(f):
    """Authenticated producer session only."""
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not (session.get("logged_in") and session.get("user_type") == "producer"):
            return jsonify({"status": "error", "message": "Producer login required"}), 403
        return f(*args, **kwargs)
    return _wrap


def _require_customer(f):
    """Authenticated customer session only."""
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not (session.get("logged_in") and session.get("user_type") == "customer"):
            return jsonify({"status": "error", "message": "Customer login required"}), 401
        return f(*args, **kwargs)
    return _wrap


def _require_admin(f):
    """Authenticated admin session only (username must be 'admin')."""
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not (session.get("logged_in") and session.get("username") == "admin"):
            return jsonify({"status": "error", "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return _wrap


def _allowed_image(filename: str, content_type: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS and content_type in ALLOWED_MIMES

# ── Auth ──────────────────────────────────────────────────────────────────────

@api.route("/auth/customer/login", methods=["POST"])
@limiter.limit("10 per minute; 50 per day")
def customer_login():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"status": "error", "message": "Please enter your credentials"}), 400

    customers_file = os.path.join(UPLOAD_FOLDER, "customers.json")
    if not os.path.exists(customers_file):
        return jsonify({"status": "error", "message": "Incorrect credentials"}), 401

    with open(customers_file, "r") as f:
        try:
            customers = json.load(f)
        except json.JSONDecodeError:
            customers = []

    customer = next((c for c in customers if c.get("username") == username), None)
    if not customer or not check_password_hash(customer.get("password_hash", ""), password):
        return jsonify({"status": "error", "message": "Incorrect credentials"}), 401

    session["user_type"] = "customer"
    session["username"]  = username
    session["logged_in"] = True
    return jsonify({"status": "success", "redirect": "/account"})


@api.route("/auth/customer/register", methods=["POST"])
@limiter.limit("5 per minute")
def customer_register():
    try:
        data     = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        name     = data.get("name",     "").strip()
        email    = data.get("email",    "").strip().lower()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not all([name, email, username, password]):
            return jsonify({"status": "error", "message": "All fields are required"})

        if not re.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$", email):
            return jsonify({"status": "error", "message": "Invalid email address"})

        if len(name) > 120:
            return jsonify({"status": "error", "message": "Name too long (max 120 characters)"})

        username_ok = validate_username(username)
        if not username_ok[0]:
            return jsonify({"status": "error", "message": username_ok[1]})

        password_ok = validate_password(password)
        if not password_ok[0]:
            return jsonify({"status": "error", "message": password_ok[1]})

        customers_file = os.path.join(UPLOAD_FOLDER, "customers.json")
        customers = []
        if os.path.exists(customers_file):
            with open(customers_file, "r") as f:
                try:
                    customers = json.load(f)
                except json.JSONDecodeError:
                    customers = []

        if any(c.get("username") == username for c in customers):
            return jsonify({"status": "error", "message": "Username already taken"})
        if any(c.get("email") == email for c in customers):
            return jsonify({"status": "error", "message": "Email address already registered"})

        customers.append({
            "username":      username,
            "name":          name,
            "email":         email,
            "password_hash": generate_password_hash(password),
            "joined":        datetime.now().strftime("%Y-%m-%d"),
            "orders":        [],
        })
        with open(customers_file, "w") as f:
            json.dump(customers, f, indent=2)

        session["user_type"] = "customer"
        session["username"]  = username
        session["logged_in"] = True
        return jsonify({"status": "success", "redirect": "/account"})

    except Exception as e:
        print(f"[customer_register] Error: {e}")
        return jsonify({"status": "error", "message": "A server error occurred. Please try again."}), 500


@api.route("/auth/producer/login", methods=["POST"])
@limiter.limit("10 per minute; 50 per day")
def producer_login():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"status": "error", "message": "Please enter your credentials"}), 400

    if check_password(username, password):
        session["user_type"] = "producer"
        session["username"]  = username
        session["logged_in"] = True
        return jsonify({"status": "success", "redirect": "/producer_dashboard"})

    return jsonify({"status": "error", "message": "Incorrect credentials"}), 401


@api.route("/auth/producer/onboarding/account", methods=["POST"])
@limiter.limit("10 per minute")
def producer_onboarding_account():
    data     = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    username_ok = validate_username(username)
    if not username_ok[0]:
        return jsonify({"status": "error", "message": username_ok[1]})

    password_ok = validate_password(password)
    if not password_ok[0]:
        return jsonify({"status": "error", "message": password_ok[1]})

    producers_file = os.path.join(UPLOAD_FOLDER, "producers.json")
    if os.path.exists(producers_file):
        with open(producers_file, "r") as f:
            try:
                producers = json.load(f)
            except json.JSONDecodeError:
                producers = []
        if any(p.get("username") == username for p in producers):
            return jsonify({"status": "error", "message": "Username already taken"})

    return jsonify({"status": "success"})


@api.route("/auth/producer/onboarding/complete", methods=["POST"])
@limiter.limit("10 per minute")
def producer_onboarding_complete():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        username    = data.get("username",    "").strip()
        password    = data.get("password",    "")
        biz_name    = data.get("name",        "").strip()
        address     = data.get("address",     "").strip()
        eircode     = data.get("eircode",     "").strip().upper()
        county      = data.get("county",      "").strip()
        phone       = data.get("phone",       "").strip()
        categories  = data.get("categories",  [])
        description = data.get("description", "").strip()

        if not all([username, password, biz_name, address, eircode, county, phone]):
            return jsonify({"status": "error", "message": "Missing required fields"})
        if not categories:
            return jsonify({"status": "error", "message": "Please select at least one category"})

        if len(biz_name) > 120:
            return jsonify({"status": "error", "message": "Business name too long (max 120 characters)"})
        if len(address) > 200:
            return jsonify({"status": "error", "message": "Address too long (max 200 characters)"})
        if len(description) > 1000:
            return jsonify({"status": "error", "message": "Description too long (max 1000 characters)"})
        if not re.match(r"^[A-Z0-9]{3}\s?[A-Z0-9]{4}$", eircode):
            return jsonify({"status": "error", "message": "Invalid Eircode format (e.g. D02 XY67)"})
        if not re.match(r"^[\d\s\+\-\(\)]{7,20}$", phone):
            return jsonify({"status": "error", "message": "Invalid telephone number"})

        producers_file = os.path.join(UPLOAD_FOLDER, "producers.json")
        producers = []
        if os.path.exists(producers_file):
            with open(producers_file, "r") as f:
                try:
                    producers = json.load(f)
                except json.JSONDecodeError:
                    producers = []

        if any(p.get("username") == username for p in producers):
            return jsonify({"status": "error", "message": "Username already taken"})

        producers.append({
            "username":      username,
            "business_name": biz_name,
            "address":       address,
            "eircode":       eircode,
            "county":        county,
            "telephone":     phone,
            "categories":    categories,
            "description":   description,
            "joined":        datetime.now().strftime("%Y-%m-%d"),
        })
        with open(producers_file, "w") as f:
            json.dump(producers, f, indent=2)

        hashed      = generate_password_hash(password)
        logins_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_logins")
        with open(logins_path, "a") as f:
            f.write(f"\n{username}={hashed}")

        session["user_type"] = "producer"
        session["username"]  = username
        session["logged_in"] = True
        return jsonify({"status": "success", "redirect": "/producer_dashboard"})

    except Exception as e:
        print(f"[producer_onboarding_complete] Error: {e}")
        return jsonify({
            "status": "error",
            "message": "A server error occurred. Your details are safe — please try again.",
        }), 500


@api.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "success", "redirect": "/"})


@api.route("/auth/me", methods=["GET"])
@_require_login
def auth_me():
    """Return safe session info — useful for mobile clients to check auth state."""
    return jsonify({
        "logged_in": True,
        "username":  session.get("username"),
        "user_type": session.get("user_type"),
    })

# ── Cart ──────────────────────────────────────────────────────────────────────

@api.route("/cart/contents", methods=["GET"])
def cart_contents():
    cart     = session.get("cart", [])
    subtotal = sum(item.get("price", 0) * item.get("qty", 1) for item in cart)
    return jsonify({"items": cart, "subtotal": round(subtotal, 2)})


@api.route("/cart/add", methods=["POST"])
@limiter.limit("120 per minute")
def cart_add():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400

    product_id = data.get("product_id")
    qty        = max(1, int(data.get("qty", 1)))

    all_products = _load_json("products.json", [])
    product      = next((p for p in all_products if p.get("id") == product_id), None)
    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    producer_username = product.get("producer", "")
    producer_name     = producer_username
    all_producers     = _load_json("producers.json", [])
    p_rec = next((p for p in all_producers if p.get("username") == producer_username), None)
    if p_rec:
        producer_name = p_rec.get("business_name", producer_username)

    cart       = session.get("cart", [])
    p_settings = _load_json("producer_settings.json", {})
    p_cfg      = p_settings.get(producer_username, {})
    existing   = next((i for i in cart if i["product_id"] == product_id), None)

    # ── Multi-producer market constraint ──────────────────────────────────────
    # Allow products from multiple producers only when all producers share
    # at least one common farmer's market (enabling market_pickup collection).
    if not existing and cart:
        existing_usernames = {i["producer_username"] for i in cart}
        if producer_username not in existing_usernames:
            new_markets = set(p_cfg.get("market_ids", []))
            all_producer_market_sets = [
                set(p_settings.get(u, {}).get("market_ids", []))
                for u in existing_usernames
            ] + [new_markets]
            shared = all_producer_market_sets[0].intersection(*all_producer_market_sets[1:])
            if not shared:
                cart_producers = [
                    next((p.get("business_name", u) for p in all_producers if p.get("username") == u), u)
                    for u in existing_usernames
                ]
                return jsonify({
                    "status":  "error",
                    "message": (
                        f"Your cart already contains items from {', '.join(cart_producers)}. "
                        "You can only mix products from different producers if they all attend "
                        "a common farmer's market. Check the Markets page to find producers "
                        "who share a market near you."
                    )
                }), 409

    if existing:
        existing["qty"] = min(existing["qty"] + qty, 99)
    else:
        cart.append({
            "product_id":        product_id,
            "name":              product.get("name", ""),
            "price":             float(product.get("price", 0)),
            "qty":               qty,
            "image":             product.get("image", ""),
            "producer_username": producer_username,
            "producer_name":     producer_name,
            "delivery_methods":  (
                product.get("delivery_methods")
                or p_cfg.get("delivery_methods")
                or ["collect_in_person", "market_pickup", "dropoff_box", "producer_delivery"]
            ),
            "pickup_locations":  p_cfg.get("pickup_locations", []),
        })

    session["cart"]    = cart
    session.modified   = True
    return jsonify({"status": "success", "cart_count": sum(i["qty"] for i in cart)})


@api.route("/cart/remove", methods=["POST"])
def cart_remove():
    data       = request.get_json(force=True, silent=True)
    product_id = data.get("product_id") if data else None
    cart       = [i for i in session.get("cart", []) if i["product_id"] != product_id]
    session["cart"]  = cart
    session.modified = True
    return jsonify({"status": "success"})


@api.route("/cart/update", methods=["POST"])
def cart_update():
    data       = request.get_json(force=True, silent=True)
    product_id = data.get("product_id") if data else None
    qty        = int(data.get("qty", 0)) if data else 0
    cart       = session.get("cart", [])
    if qty <= 0:
        cart = [i for i in cart if i["product_id"] != product_id]
    else:
        for item in cart:
            if item["product_id"] == product_id:
                item["qty"] = min(qty, 99)
                break
    session["cart"]  = cart
    session.modified = True
    return jsonify({"status": "success"})

# ── Checkout ──────────────────────────────────────────────────────────────────

@api.route("/checkout/submit", methods=["POST"])
@limiter.limit("10 per minute")
def checkout_submit():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        cart = session.get("cart", [])
        if not cart:
            return jsonify({"status": "error", "message": "Your cart is empty"}), 400

        delivery_method = data.get("delivery_method", "producer_delivery").strip()
        needs_address   = delivery_method == "producer_delivery"
        delivery_fee    = DELIVERY_FEES.get(delivery_method, 3.99)

        contact_required = ["first_name", "last_name", "email", "phone"]
        address_required = ["address", "town", "eircode"] if needs_address else []
        for field in contact_required + address_required:
            if not data.get(field, "").strip():
                return jsonify({
                    "status":  "error",
                    "message": f"Missing field: {field.replace('_', ' ')}",
                }), 400

        if not re.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$", data["email"].strip().lower()):
            return jsonify({"status": "error", "message": "Invalid email address"}), 400

        subtotal = sum(item.get("price", 0) * item.get("qty", 1) for item in cart)
        discount = 0.0

        coupon_code = data.get("coupon_code", "").strip().upper()
        if coupon_code:
            all_coupons = _load_json("coupons.json", [])
            coupon = next(
                (c for c in all_coupons if c.get("code") == coupon_code and c.get("active")),
                None,
            )
            if coupon:
                if coupon.get("type") == "percent":
                    discount = round(subtotal * coupon["amount"] / 100, 2)
                else:
                    discount = min(float(coupon.get("amount", 0)), subtotal)
                coupon["uses"] = coupon.get("uses", 0) + 1
                if coupon.get("max_uses") and coupon["uses"] >= coupon["max_uses"]:
                    coupon["active"] = False
                _save_json("coupons.json", all_coupons)

        total = round(max(0, subtotal + delivery_fee - discount), 2)

        orders   = _load_json("orders.json", [])
        numeric_ids = [o["id"] for o in orders if isinstance(o.get("id"), int)]
        order_id = max(numeric_ids, default=0) + 1
        all_contact_fields = ["first_name", "last_name", "email", "phone", "address", "town", "eircode"]
        order = {
            "id":              order_id,
            "customer":        session.get("username"),
            "delivery":        {k: data.get(k, "") for k in all_contact_fields},
            "delivery_method": delivery_method,
            "items":           cart,
            "subtotal":        round(subtotal, 2),
            "discount":        discount,
            "delivery_fee":    delivery_fee,
            "total":           total,
            "coupon":          coupon_code or None,
            "status":          "pending",
            "date":            datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        orders.append(order)
        _save_json("orders.json", orders)

        if session.get("user_type") == "customer" and session.get("username"):
            customers = _load_json("customers.json", [])
            for c in customers:
                if c.get("username") == session["username"]:
                    c.setdefault("orders", []).append({
                        "id":     order_id,
                        "date":   order["date"],
                        "total":  total,
                        "status": "pending",
                        "items":  len(cart),
                    })
                    break
            _save_json("customers.json", customers)

        session["cart"]  = []
        session.modified = True
        return jsonify({"status": "success", "order_id": order_id})

    except Exception as e:
        print(f"[checkout_submit] Error: {e}")
        return jsonify({"status": "error", "message": "Server error — please try again."}), 500

# ── Coupons ───────────────────────────────────────────────────────────────────

@api.route("/coupons", methods=["GET"])
@_require_producer
def get_coupons():
    username = session["username"]
    coupons  = [c for c in _load_json("coupons.json", []) if c.get("producer_username") == username]
    return jsonify({"status": "success", "coupons": coupons})


@api.route("/coupons/create", methods=["POST"])
@_require_producer
@limiter.limit("20 per minute")
def create_coupon():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400

    code      = data.get("code", "").strip().upper()
    dtype     = data.get("type", "percent")
    amount    = float(data.get("amount", 0))
    min_order = float(data.get("min_order", 0))
    max_uses  = int(data.get("max_uses", 0)) or None
    expires   = data.get("expiry", "").strip() or None

    if not code or not re.match(r"^[A-Z0-9_-]{3,20}$", code):
        return jsonify({"status": "error", "message": "Code must be 3–20 alphanumeric characters (hyphens/underscores allowed)"})
    if amount <= 0:
        return jsonify({"status": "error", "message": "Discount amount must be > 0"})
    if dtype == "percent" and amount > 100:
        return jsonify({"status": "error", "message": "Percentage cannot exceed 100"})

    coupons = _load_json("coupons.json", [])
    if any(c.get("code") == code for c in coupons):
        return jsonify({"status": "error", "message": "Coupon code already exists"})

    coupons.append({
        "id":                len(coupons) + 1,
        "code":              code,
        "type":              dtype,
        "amount":            amount,
        "min_order":         min_order,
        "max_uses":          max_uses,
        "uses":              0,
        "expiry":            expires,
        "producer_username": session["username"],
        "active":            True,
        "created":           datetime.now().strftime("%Y-%m-%d"),
    })
    _save_json("coupons.json", coupons)
    return jsonify({"status": "success"})


@api.route("/coupons/delete", methods=["POST"])
@_require_producer
def delete_coupon():
    data     = request.get_json(force=True, silent=True)
    code     = data.get("code", "").strip().upper() if data else ""
    username = session["username"]
    coupons  = _load_json("coupons.json", [])
    updated  = [c for c in coupons if not (c.get("code") == code and c.get("producer_username") == username)]
    if len(updated) == len(coupons):
        return jsonify({"status": "error", "message": "Coupon not found"})
    _save_json("coupons.json", updated)
    return jsonify({"status": "success"})


@api.route("/coupons/validate", methods=["GET"])
@limiter.limit("30 per minute")
def validate_coupon():
    code  = request.args.get("code", "").strip().upper()
    total = float(request.args.get("total", 0) or 0)
    if not code:
        return jsonify({"status": "error", "message": "No code provided"})

    coupons = _load_json("coupons.json", [])
    coupon  = next((c for c in coupons if c.get("code") == code and c.get("active")), None)
    if not coupon:
        return jsonify({"status": "error", "message": "Invalid or expired coupon"})

    if coupon.get("expiry"):
        try:
            if date.fromisoformat(coupon["expiry"]) < date.today():
                return jsonify({"status": "error", "message": "This coupon has expired"})
        except ValueError:
            pass

    if coupon.get("max_uses") and coupon.get("uses", 0) >= coupon["max_uses"]:
        return jsonify({"status": "error", "message": "Coupon has reached its usage limit"})

    if total < coupon.get("min_order", 0):
        return jsonify({"status": "error", "message": f"Minimum order €{coupon['min_order']:.2f} required"})

    discount = (
        round(total * coupon["amount"] / 100, 2)
        if coupon["type"] == "percent"
        else min(float(coupon["amount"]), total)
    )
    label = f"{int(coupon['amount'])}%" if coupon["type"] == "percent" else f"€{coupon['amount']:.2f}"
    return jsonify({
        "status":   "success",
        "code":     code,
        "discount": discount,
        "message":  f"{label} discount applied!",
    })

# ── Products ──────────────────────────────────────────────────────────────────

@api.route("/products/add", methods=["POST"])
@_require_login
def add_product():
    file      = request.files.get("image")
    image_url = None

    if file and file.filename:
        if not _allowed_image(file.filename, file.content_type or ""):
            return jsonify({"status": "error", "message": "Invalid file type. Only PNG, JPG, GIF and WEBP images are allowed."}), 400
        # Read ahead to check size before saving
        content = file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            return jsonify({"status": "error", "message": "File is too large (max 5MB)"}), 413

        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        with open(os.path.join(UPLOAD_FOLDER, filename), "wb") as f:
            f.write(content)
        image_url = f"/static/{filename}"
    else:
        image_url = "https://via.placeholder.com/150/cccccc/666666?text=No+Image"

    name        = request.form.get("name",        "")[:200]
    description = request.form.get("description", "")[:1000]
    stock       = request.form.get("stock",       "0")
    price       = request.form.get("price",       "0")
    category    = request.form.get("category",    "")
    producer    = session.get("username")

    all_products = _load_json("products.json", [])
    new_id       = max((p.get("id", 0) for p in all_products), default=0) + 1
    all_products.append({
        "id":          new_id,
        "name":        name,
        "description": description,
        "price":       float(price),
        "stock":       int(stock),
        "category":    category,
        "image":       image_url,
        "producer":    producer,
    })
    _save_json("products.json", all_products)

    return jsonify({
        "status":    "success",
        "message":   "Product added successfully",
        "image_url": image_url,
        "product_id": new_id,
    }), 200


@api.route("/products/update-stock", methods=["POST"])
@_require_login
def update_stock():
    data       = request.get_json(force=True, silent=True)
    product_id = data.get("id") if data else None
    new_stock  = data.get("stock") if data else None

    if product_id is None or new_stock is None:
        return jsonify({"status": "error", "message": "Missing product ID or stock level"}), 400

    products_file = os.path.join(UPLOAD_FOLDER, "products.json")
    try:
        with open(products_file, "r") as f:
            products = json.load(f)

        found = False
        for p in products:
            if p.get("id") == int(product_id):
                p["stock"] = int(new_stock)
                found = True
                break

        if not found:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        with open(products_file, "w") as f:
            json.dump(products, f, indent=2)

        return jsonify({"status": "success", "message": "Stock updated successfully"}), 200
    except Exception as e:
        print(f"[update_stock] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@api.route("/search", methods=["GET"])
@limiter.limit("60 per minute")
def search():
    query = request.args.get("q", "").lower().strip()
    if not query or len(query) > 100:
        return jsonify([])

    products_file = os.path.join(UPLOAD_FOLDER, "products.json")
    try:
        with open(products_file, "r") as f:
            products = json.load(f)
        results = [
            p for p in products
            if query in p.get("name", "").lower() or query in p.get("description", "").lower()
        ]
        return jsonify(results)
    except Exception as e:
        print(f"[search] Error: {e}")
        return jsonify([])

# ── Public catalogue data ─────────────────────────────────────────────────────

@api.route("/products", methods=["GET"])
def get_products():
    """All products, each enriched with the producer's display name."""
    all_products  = _load_json("products.json", [])
    all_producers = _load_json("producers.json", [])
    producer_info = {
        p.get("username"): {
            "name": p.get("business_name", p.get("username", "")),
            "county": p.get("county", "")
        }
        for p in all_producers
    }
    enriched = []
    for p in all_products:
        item = dict(p)
        uname = p.get("producer", "")
        info = producer_info.get(uname, {})
        item["producer_display"] = info.get("name", uname)
        item["producer_county"] = info.get("county", "")
        enriched.append(item)
    categories = sorted({p.get("category", "") for p in all_products if p.get("category")})
    counties = sorted({item["producer_county"] for item in enriched if item["producer_county"]})
    return jsonify({"products": enriched, "categories": categories, "counties": counties})


@api.route("/markets", methods=["GET"])
@limiter.limit("60 per minute")
def get_markets():
    """All markets enriched with the producers who attend them and their in-stock products."""
    markets       = _load_json("markets.json", [])
    all_settings  = _load_json("producer_settings.json", {})
    all_producers = _load_json("producers.json", [])
    all_products  = _load_json("products.json", [])

    producer_lookup = {p["username"]: p for p in all_producers}

    products_by_producer: dict = {}
    for prod in all_products:
        u = prod.get("producer", "")
        products_by_producer.setdefault(u, []).append(prod)

    # Reverse index: market_id -> [producer_username, ...]
    market_producers: dict = {}
    for username, cfg in all_settings.items():
        for mid in cfg.get("market_ids", []):
            market_producers.setdefault(mid, []).append(username)

    enriched = []
    for market in markets:
        mid = market["id"]
        attending = []
        for u in market_producers.get(mid, []):
            p_rec = producer_lookup.get(u)
            if not p_rec:
                continue
            attending.append({
                "username":      u,
                "business_name": p_rec.get("business_name", u),
                "county":        p_rec.get("county", ""),
                "products": [
                    {k: v for k, v in prod.items()}
                    for prod in products_by_producer.get(u, [])
                    if prod.get("stock", 0) > 0
                ],
            })
        item = dict(market)
        item["attending_producers"] = attending
        enriched.append(item)

    counties = sorted({m["county"] for m in markets if m.get("county")})
    return jsonify({"markets": enriched, "counties": counties})


@api.route("/producers", methods=["GET"])
def get_producers():
    """All producer profiles with a product_count field added."""
    all_producers  = _load_json("producers.json", [])
    all_products   = _load_json("products.json", [])
    product_counts: dict = {}
    for p in all_products:
        u = p.get("producer", "")
        product_counts[u] = product_counts.get(u, 0) + 1
    result = []
    for p in all_producers:
        item = dict(p)
        item["product_count"] = product_counts.get(p.get("username", ""), 0)
        result.append(item)
    return jsonify({"producers": result})


@api.route("/producers/<username>", methods=["GET"])
def get_producer_profile(username):
    """Single producer profile + their product listings."""
    all_producers = _load_json("producers.json", [])
    producer = next((p for p in all_producers if p.get("username") == username), None)
    if not producer:
        return jsonify({"status": "error", "message": "Producer not found"}), 404
    all_products = _load_json("products.json", [])
    products = [p for p in all_products if p.get("producer") == username]
    return jsonify({"producer": producer, "products": products})


# ── Customer account data ─────────────────────────────────────────────────────

@api.route("/account/me", methods=["GET"])
@_require_customer
def account_me():
    """Return the authenticated customer's profile (password hash stripped)."""
    username      = session["username"]
    customers_file = os.path.join(UPLOAD_FOLDER, "customers.json")
    customer: dict = {}
    if os.path.exists(customers_file):
        with open(customers_file, "r") as f:
            try:
                customers = json.load(f)
                customer  = next((c for c in customers if c.get("username") == username), {})
            except json.JSONDecodeError:
                pass
    safe = {k: v for k, v in customer.items() if k != "password_hash"}
    return jsonify(safe)

# ── Producer settings ─────────────────────────────────────────────────────────

@api.route("/producer/settings", methods=["GET"])
@_require_producer
def get_producer_settings():
    username = session["username"]
    settings = _load_json("producer_settings.json", {})
    return jsonify({"status": "success", "settings": settings.get(username, {})})


@api.route("/producer/settings", methods=["POST"])
@_require_producer
@limiter.limit("30 per minute")
def save_producer_settings():
    username = session["username"]
    data     = request.get_json(force=True, silent=True) or {}
    settings = _load_json("producer_settings.json", {})
    existing = settings.get(username, {})

    if "payment_methods" in data:
        allowed = {"card", "cash_collection", "cash_delivery"}
        existing["payment_methods"] = [m for m in data["payment_methods"] if m in allowed]

    if "delivery_methods" in data:
        allowed = {"collect_in_person", "market_pickup", "dropoff_box", "producer_delivery"}
        existing["delivery_methods"] = [m for m in data["delivery_methods"] if m in allowed]

    if "pickup_locations" in data:
        locs = []
        for loc in data["pickup_locations"][:20]:
            if not loc.get("name"):
                continue
            locs.append({
                "id":      loc.get("id") or str(len(locs) + 1),
                "name":    str(loc.get("name",    ""))[:100],
                "address": str(loc.get("address", ""))[:200],
                "lat":     float(loc["lat"]) if loc.get("lat") else None,
                "lng":     float(loc["lng"]) if loc.get("lng") else None,
                "w3w":     str(loc.get("w3w",  ""))[:80],
                "type":    str(loc.get("type", "farm"))[:30],
            })
        existing["pickup_locations"] = locs

    if "market_ids" in data:
        all_markets  = _load_json("markets.json", [])
        valid_ids    = {m["id"] for m in all_markets}
        existing["market_ids"] = [mid for mid in data["market_ids"] if mid in valid_ids]

    settings[username] = existing
    _save_json("producer_settings.json", settings)
    return jsonify({"status": "success"})


@api.route("/producer/pickup-locations", methods=["GET"])
def get_pickup_locations():
    """Public — returns pickup locations for producers listed in the cart."""
    usernames = request.args.getlist("u")
    if not usernames:
        return jsonify({})
    settings = _load_json("producer_settings.json", {})
    result   = {}
    for u in usernames[:10]:
        cfg      = settings.get(u, {})
        result[u] = {
            "pickup_locations": cfg.get("pickup_locations", []),
            "delivery_methods": cfg.get(
                "delivery_methods",
                ["collect_in_person", "market_pickup", "dropoff_box", "producer_delivery"],
            ),
        }
    return jsonify(result)


@api.route("/producer/product-delivery", methods=["POST"])
@_require_producer
@limiter.limit("60 per minute")
def update_product_delivery():
    data       = request.get_json(force=True, silent=True) or {}
    product_id = data.get("product_id")
    methods    = data.get("delivery_methods", [])
    username   = session["username"]

    allowed = {"collect_in_person", "market_pickup", "dropoff_box", "producer_delivery"}
    methods = [m for m in methods if m in allowed]

    products = _load_json("products.json", [])
    updated  = False
    for p in products:
        if p.get("id") == int(product_id) and p.get("producer") == username:
            p["delivery_methods"] = methods
            updated = True
            break

    if not updated:
        return jsonify({"status": "error", "message": "Product not found or not yours"}), 404

    _save_json("products.json", products)
    return jsonify({"status": "success"})


# ─────────────────────────────────────────────────────────────────────────────
# Admin analytics
# ─────────────────────────────────────────────────────────────────────────────

def _parse_order_total(order) -> float:
    """Safely extract a numeric total from either old (string) or new (float) order format."""
    t = order.get("total", 0)
    if isinstance(t, (int, float)):
        return float(t)
    # Old format: "€15.50"
    try:
        return float(str(t).replace("€", "").strip())
    except (ValueError, TypeError):
        return 0.0


@api.route("/admin/analytics", methods=["GET"])
@_require_admin
@limiter.limit("30 per minute")
def admin_analytics():
    orders     = _load_json("orders.json",   [])
    customers  = _load_json("customers.json", [])
    producers  = _load_json("producers.json", [])
    products   = _load_json("products.json",  [])
    markets    = _load_json("markets.json",   [])
    settings   = _load_json("producer_settings.json", {})

    # ── Overview ──────────────────────────────────────────────────────────────
    total_revenue = sum(_parse_order_total(o) for o in orders)
    overview = {
        "total_customers":  len(customers),
        "total_producers":  len(producers),
        "total_products":   len(products),
        "total_orders":     len(orders),
        "total_revenue":    round(total_revenue, 2),
        "active_markets":   len(markets),
        "avg_order_value":  round(total_revenue / len(orders), 2) if orders else 0.0,
        "low_stock_products": sum(1 for p in products if 0 < int(p.get("stock", 0)) <= 5),
        "out_of_stock_products": sum(1 for p in products if int(p.get("stock", 0)) == 0),
    }

    # ── Revenue / orders by date ───────────────────────────────────────────────
    date_map: dict = {}
    for o in orders:
        raw = o.get("date", "")
        day = raw[:10] if raw else "unknown"
        entry = date_map.setdefault(day, {"date": day, "count": 0, "revenue": 0.0})
        entry["count"]   += 1
        entry["revenue"] += _parse_order_total(o)
    orders_by_date = sorted(date_map.values(), key=lambda x: x["date"])
    for e in orders_by_date:
        e["revenue"] = round(e["revenue"], 2)

    # ── Top products ───────────────────────────────────────────────────────────
    product_stats: dict = {}
    for o in orders:
        for item in o.get("items", []):
            pid  = str(item.get("product_id", ""))
            name = item.get("name", pid)
            key  = pid or name
            s = product_stats.setdefault(key, {"name": name, "orders": 0, "qty": 0, "revenue": 0.0})
            qty = int(item.get("qty", 1))
            s["orders"]  += 1
            s["qty"]     += qty
            s["revenue"] += float(item.get("price", 0)) * qty
    top_products = sorted(product_stats.values(), key=lambda x: x["qty"], reverse=True)[:10]
    for p in top_products:
        p["revenue"] = round(p["revenue"], 2)

    # ── Top producers ──────────────────────────────────────────────────────────
    producer_stats: dict = {}
    producer_names = {p["username"]: p.get("business_name", p["username"]) for p in producers}
    for o in orders:
        for item in o.get("items", []):
            u  = item.get("producer_username", "")
            bn = item.get("producer_name") or producer_names.get(u, u)
            s  = producer_stats.setdefault(u, {"username": u, "business_name": bn, "orders": 0, "qty": 0, "revenue": 0.0})
            qty = int(item.get("qty", 1))
            s["orders"]  += 1
            s["qty"]     += qty
            s["revenue"] += float(item.get("price", 0)) * qty
    top_producers = sorted(producer_stats.values(), key=lambda x: x["revenue"], reverse=True)[:10]
    for p in top_producers:
        p["revenue"] = round(p["revenue"], 2)

    # ── Category breakdown ─────────────────────────────────────────────────────
    product_cat = {str(p.get("id", "")): p.get("category", "Uncategorised") for p in products}
    cat_stats: dict = {}
    for o in orders:
        for item in o.get("items", []):
            cat = product_cat.get(str(item.get("product_id", "")), "Uncategorised")
            qty = int(item.get("qty", 1))
            s   = cat_stats.setdefault(cat, {"category": cat, "qty": 0, "revenue": 0.0})
            s["qty"]     += qty
            s["revenue"] += float(item.get("price", 0)) * qty
    category_breakdown = sorted(cat_stats.values(), key=lambda x: x["qty"], reverse=True)
    for c in category_breakdown:
        c["revenue"] = round(c["revenue"], 2)

    # ── Delivery method breakdown ──────────────────────────────────────────────
    delivery_counts: dict = {}
    for o in orders:
        method = o.get("delivery_method") or "unknown"
        delivery_counts[method] = delivery_counts.get(method, 0) + 1

    # ── Orders by county ──────────────────────────────────────────────────────
    county_stats: dict = {}
    for o in orders:
        delivery = o.get("delivery") or {}
        eircode  = delivery.get("eircode", "")
        town     = delivery.get("town", "")
        # Best-effort county resolution: look up producer county for non-delivery orders
        county   = delivery.get("county") or ""
        if not county and eircode:
            county = "Unknown"   # eircode routing not implemented
        label = county or town or "Unknown"
        s = county_stats.setdefault(label, {"location": label, "count": 0, "revenue": 0.0})
        s["count"]   += 1
        s["revenue"] += _parse_order_total(o)
    orders_by_location = sorted(county_stats.values(), key=lambda x: x["count"], reverse=True)[:15]
    for e in orders_by_location:
        e["revenue"] = round(e["revenue"], 2)

    # ── Customer growth (cumulative by join date) ─────────────────────────────
    join_dates = sorted(c.get("joined", "unknown") for c in customers if c.get("joined"))
    growth = []
    for i, d in enumerate(join_dates, 1):
        growth.append({"date": d, "cumulative": i})

    # ── Producer counties breakdown ───────────────────────────────────────────
    producer_county_map: dict = {}
    for p in producers:
        county = p.get("county", "Unknown") or "Unknown"
        producer_county_map[county] = producer_county_map.get(county, 0) + 1
    producer_counties = [{"county": k, "count": v} for k, v in
                         sorted(producer_county_map.items(), key=lambda x: x[1], reverse=True)]

    # ── Market attendance (producers per market) ──────────────────────────────
    market_name_map = {m["id"]: m["name"] for m in markets}
    market_attendance: dict = {}
    for username, cfg in settings.items():
        for mid in cfg.get("market_ids", []):
            s = market_attendance.setdefault(mid, {"market_id": mid, "name": market_name_map.get(mid, mid), "producer_count": 0})
            s["producer_count"] += 1
    market_attendance_list = sorted(market_attendance.values(), key=lambda x: x["producer_count"], reverse=True)

    # ── Recent orders (last 20, most recent first) ────────────────────────────
    def _order_sort_key(o):
        raw = o.get("date", "")
        return raw if raw else ""
    recent_orders = sorted(orders, key=_order_sort_key, reverse=True)[:20]
    # Sanitise for JSON — strip password-adjacent fields
    safe_orders = []
    for o in recent_orders:
        safe_orders.append({
            "id":              o.get("id"),
            "customer":        o.get("customer") or (o.get("delivery") or {}).get("email", "guest"),
            "date":            o.get("date", ""),
            "total":           _parse_order_total(o),
            "status":          o.get("status", ""),
            "delivery_method": o.get("delivery_method", ""),
            "item_count":      sum(int(i.get("qty", 1)) for i in o.get("items", [])),
        })

    return jsonify({
        "overview":           overview,
        "orders_by_date":     orders_by_date,
        "top_products":       top_products,
        "top_producers":      top_producers,
        "category_breakdown": category_breakdown,
        "delivery_counts":    delivery_counts,
        "orders_by_location": orders_by_location,
        "customer_growth":    growth,
        "producer_counties":  producer_counties,
        "market_attendance":  market_attendance_list,
        "recent_orders":      safe_orders,
    })
