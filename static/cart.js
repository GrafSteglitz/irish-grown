/* ─────────────────────────────────────────────────────────────
   cart.js  –  Irish Grown shopping cart & checkout
   ───────────────────────────────────────────────────────────── */

const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content ?? '';
const _isLoggedInCustomer = () =>
  document.querySelector('meta[name="app-logged-in-customer"]')?.content === 'true';

async function _post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() },
    body: JSON.stringify(body)
  });
  return res.json();
}

/* ── Delivery method config ───────────────────────────────── */
const DELIVERY_LABELS = {
  collect_in_person: 'Collect in Person',
  market_pickup:     'Market Pick-up',
  dropoff_box:       'Locked Drop-Off Box',
  producer_delivery: 'Producer to Customer Delivery',
};
const DELIVERY_FEES = {
  collect_in_person: 0,
  market_pickup:     0,
  dropoff_box:       0,
  producer_delivery: 3.99,
};
const DELIVERY_DESCRIPTIONS = {
  collect_in_person: 'Pick up your order directly from the producer\'s farm or premises. You\'ll be contacted with the collection address and available time slots after placing your order. No delivery fee applies.',
  market_pickup:     'Collect your order from a local farmers\' market stall. Check the map for available market locations and dates. No delivery fee applies.',
  dropoff_box:       'Your order will be left in a secure, locked collection box near you. You\'ll receive a PIN code by email once your order is ready to collect. No delivery fee applies.',
  producer_delivery: 'The producer delivers your order directly to your door. A delivery fee of €3.99 applies. Estimated delivery: 1–3 business days after your order is confirmed.',
};
const DELIVERY_ORDER = ['collect_in_person', 'market_pickup', 'dropoff_box', 'producer_delivery'];

let _lastCartItems    = [];
let _selectedDelivery = 'producer_delivery';
let _coMap            = null;
let _accountData      = null;

/* ── Drawer open / close ──────────────────────────────────── */
function cartOpen() {
  document.getElementById('cart-drawer').classList.add('open');
  document.getElementById('cart-backdrop').classList.add('open');
  document.body.style.overflow = 'hidden';
  cartShowCart();
}
function cartClose() {
  document.getElementById('cart-drawer').classList.remove('open');
  document.getElementById('cart-backdrop').classList.remove('open');
  document.body.style.overflow = '';
}
function cartShowCart() {
  const cv = document.getElementById('cart-view');
  cv.style.display = 'flex';
  cv.style.flexDirection = 'column';
  document.getElementById('checkout-view').style.display = 'none';
  document.getElementById('checkout-success').style.display = 'none';
}
function cartShowCheckout() {
  document.getElementById('cart-view').style.display = 'none';
  const cv = document.getElementById('checkout-view');
  cv.style.display = 'flex';
  cv.style.flexDirection = 'column';
  document.getElementById('checkout-success').style.display = 'none';

  // Sync subtotal from cart view
  const sub = document.getElementById('cart-subtotal')?.textContent || '€0.00';
  const subEl = document.getElementById('co-subtotal');
  if (subEl) subEl.textContent = sub;

  // For logged-in customers, pre-fill contact from account
  if (_isLoggedInCustomer()) {
    _loadAccountContact();
  }

  // Populate delivery methods (recalculates total)
  _populateDeliveryMethods(_lastCartItems);

  lucide.createIcons();
}

async function _loadAccountContact() {
  try {
    const res  = await fetch('/api/account/me');
    const data = await res.json();
    if (!data.username) return;
    const nameParts = (data.name || '').trim().split(/\s+/);
    _accountData = {
      ...data,
      first_name: nameParts[0] || '',
      last_name:  nameParts.slice(1).join(' ') || '',
    };
    const summaryEl = document.getElementById('co-account-summary');
    const guestEl   = document.getElementById('co-guest-fields');
    if (summaryEl) {
      summaryEl.innerHTML = `
        <div class="co-account-summary-box">
          <div class="co-account-summary-label">Ordering as</div>
          <div class="co-account-summary-name">${_esc(data.name || data.username)}</div>
          <div class="co-account-summary-email">${_esc(data.email || '')}</div>
        </div>`;
      summaryEl.style.display = '';
    }
    if (guestEl) guestEl.style.display = 'none';
  } catch { /* fall back to guest form */ }
}

/* ── Badge update ─────────────────────────────────────────── */
function _updateBadge(count) {
  const badge = document.getElementById('cart-badge');
  if (!badge) return;
  if (count > 0) { badge.textContent = count > 99 ? '99+' : count; badge.style.display = 'flex'; }
  else { badge.style.display = 'none'; }
}

/* ── Render cart items ────────────────────────────────────── */
function _renderCart(items) {
  _lastCartItems = items || [];
  const container = document.getElementById('cart-items');
  const footer    = document.getElementById('cart-footer');
  const empty     = document.getElementById('cart-empty');
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = '';
    if (empty) { container.appendChild(empty); empty.style.display = 'flex'; }
    if (footer) footer.style.display = 'none';
    _updateBadge(0);
    return;
  }

  if (empty) empty.style.display = 'none';

  const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0);
  const count    = items.reduce((s, i) => s + i.qty, 0);

  const subEl = document.getElementById('cart-subtotal');
  const totEl = document.getElementById('cart-total');
  if (subEl) subEl.textContent = `€${subtotal.toFixed(2)}`;
  // Cart footer shows max delivery (€3.99) as worst-case estimate
  if (totEl) totEl.textContent = `€${(subtotal + 3.99).toFixed(2)}`;
  if (footer) footer.style.display = 'block';
  _updateBadge(count);

  const imgSrc = item => {
    if (item.image_url) return item.image_url;
    if (item.image)     return '/static/' + item.image;
    return '';
  };

  container.innerHTML = items.map(item => `
    <div class="cart-item" data-id="${item.product_id}">
      <img class="cart-item-img"
           src="${_esc(imgSrc(item))}"
           alt="${_esc(item.name)}"
           onerror="this.src='/static/eggs.png'">
      <div class="cart-item-info">
        <div class="cart-item-name">${_esc(item.name)}</div>
        <div class="cart-item-producer">${_esc(item.producer_name || '')}</div>
        <div class="cart-item-price">€${(item.price * item.qty).toFixed(2)}
          <span style="opacity:.5;font-size:.72rem"> ×${item.qty} @ €${item.price.toFixed(2)}</span>
        </div>
      </div>
      <div class="cart-item-controls">
        <button class="qty-btn" onclick="cartUpdate(${item.product_id}, ${item.qty - 1})">−</button>
        <span class="qty-display">${item.qty}</span>
        <button class="qty-btn" onclick="cartUpdate(${item.product_id}, ${item.qty + 1})">+</button>
        <button class="remove-btn" onclick="cartRemove(${item.product_id})" title="Remove">
          <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" width="13" height="13">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>
          </svg>
        </button>
      </div>
    </div>
  `).join('');

  lucide.createIcons();
}

function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Fetch fresh cart from server ─────────────────────────── */
async function cartRefresh() {
  try {
    const res  = await fetch('/api/cart/contents');
    const data = await res.json();
    _renderCart(data.items || []);
  } catch { /* silent */ }
}

/* ── Add to cart ──────────────────────────────────────────── */
async function cartAdd(productId, qty) {
  qty = parseInt(qty) || 1;
  try {
    const data = await _post('/api/cart/add', { product_id: productId, qty });
    if (data.status === 'success') {
      await cartRefresh();
      cartOpen();
    } else {
      alert(data.message || 'Could not add item to cart.');
    }
  } catch { alert('Network error — please try again.'); }
}

/* ── Update quantity ──────────────────────────────────────── */
async function cartUpdate(productId, qty) {
  if (qty < 1) { cartRemove(productId); return; }
  try {
    await _post('/api/cart/update', { product_id: productId, qty });
    await cartRefresh();
  } catch { /* ignore */ }
}

/* ── Remove item ──────────────────────────────────────────── */
async function cartRemove(productId) {
  try {
    await _post('/api/cart/remove', { product_id: productId });
    await cartRefresh();
  } catch { /* ignore */ }
}

/* ── Delivery method selector ─────────────────────────────── */
function _populateDeliveryMethods(items) {
  const container = document.getElementById('co-delivery-methods');
  if (!container) return;

  // Union of all delivery methods available across cart items
  const available = new Set();
  items.forEach(item => {
    (item.delivery_methods || DELIVERY_ORDER).forEach(m => available.add(m));
  });
  if (available.size === 0) DELIVERY_ORDER.forEach(m => available.add(m));

  const methods = DELIVERY_ORDER.filter(m => available.has(m));
  _selectedDelivery = methods[0] || 'producer_delivery';

  container.innerHTML = methods.map((m, i) => `
    <div class="co-delivery-wrapper">
      <div class="co-delivery-row">
        <label class="co-delivery-option${i === 0 ? ' selected' : ''}">
          <input type="radio" name="co-delivery-method" value="${m}" ${i === 0 ? 'checked' : ''}>
          <span class="co-delivery-label">${DELIVERY_LABELS[m] || m}</span>
          <span class="co-delivery-fee">${DELIVERY_FEES[m] === 0 ? 'Free' : '€' + DELIVERY_FEES[m].toFixed(2)}</span>
        </label>
        <button type="button" class="co-delivery-toggle" onclick="_toggleDeliveryDesc(this)" title="What does this involve?">
          <i data-lucide="chevron-down"></i>
        </button>
      </div>
      <div class="co-delivery-desc">${DELIVERY_DESCRIPTIONS[m] || ''}</div>
    </div>
  `).join('');

  container.querySelectorAll('input[name="co-delivery-method"]').forEach(radio => {
    radio.addEventListener('change', () => {
      container.querySelectorAll('.co-delivery-option').forEach(l => l.classList.remove('selected'));
      radio.closest('.co-delivery-option').classList.add('selected');
      _selectedDelivery = radio.value;
      _onDeliveryMethodChange(radio.value, items);
    });
  });

  _onDeliveryMethodChange(_selectedDelivery, items);
}

function _toggleDeliveryDesc(btn) {
  const wrapper = btn.closest('.co-delivery-wrapper');
  const desc    = wrapper.querySelector('.co-delivery-desc');
  const isOpen  = desc.classList.toggle('open');
  btn.classList.toggle('open', isOpen);
  lucide.createIcons();
}

function _onDeliveryMethodChange(method, items) {
  const addressSection = document.getElementById('co-address-section');
  const mapSection     = document.getElementById('co-map-section');
  const feeEl          = document.getElementById('co-delivery-fee');
  const totEl          = document.getElementById('co-total');
  const subEl          = document.getElementById('co-subtotal');
  const discEl         = document.getElementById('co-discount-val');

  if (addressSection) addressSection.style.display = (method === 'producer_delivery') ? '' : 'none';

  const fee = DELIVERY_FEES[method] ?? 3.99;
  if (feeEl) feeEl.textContent = fee === 0 ? 'Free' : `€${fee.toFixed(2)}`;

  const subtotal = parseFloat((subEl?.textContent || '0').replace('€', '')) || 0;
  const discount = discEl ? parseFloat((discEl.textContent || '0').replace('−€', '')) || 0 : 0;
  if (totEl) totEl.textContent = `€${Math.max(0, subtotal + fee - discount).toFixed(2)}`;

  const isPickup = (method !== 'producer_delivery');
  if (mapSection) {
    mapSection.style.display = isPickup ? '' : 'none';
    if (isPickup && items) _showPickupMap(items);
  }
}

function _showPickupMap(items) {
  const mapEl  = document.getElementById('co-map');
  const infoEl = document.getElementById('co-map-info');
  if (!mapEl || typeof L === 'undefined') return;

  // Collect pickup locations from cart items, deduplicated by producer
  const seen = new Set();
  const locations = [];
  items.forEach(item => {
    if (!seen.has(item.producer_username) && item.pickup_locations?.length) {
      seen.add(item.producer_username);
      item.pickup_locations.forEach(loc => {
        if (loc.lat != null && loc.lng != null) {
          locations.push({ ...loc, producer_name: item.producer_name });
        }
      });
    }
  });

  if (!_coMap) {
    _coMap = L.map('co-map', { zoomControl: true }).setView([53.4, -8.0], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(_coMap);
  } else {
    _coMap.eachLayer(layer => { if (layer instanceof L.Marker) _coMap.removeLayer(layer); });
  }

  // Invalidate after display:none → display:block transition
  setTimeout(() => _coMap.invalidateSize(), 80);

  if (locations.length === 0) {
    if (infoEl) infoEl.textContent = 'Contact the producer(s) for pickup location details.';
    return;
  }

  const bounds = [];
  locations.forEach(loc => {
    let html = `<strong>${_esc(loc.name)}</strong>`;
    if (loc.address) html += `<br>${_esc(loc.address)}`;
    if (loc.w3w)     html += `<br><span style="color:#4cd98a">///what3words: ${_esc(loc.w3w)}</span>`;
    if (loc.producer_name) html += `<br><em>${_esc(loc.producer_name)}</em>`;
    L.marker([loc.lat, loc.lng]).addTo(_coMap).bindPopup(html);
    bounds.push([loc.lat, loc.lng]);
  });

  if (bounds.length === 1) {
    _coMap.setView(bounds[0], 14);
  } else {
    _coMap.fitBounds(bounds, { padding: [24, 24] });
  }

  if (infoEl) {
    infoEl.innerHTML = locations.map(loc => {
      let txt = `<strong>${_esc(loc.name)}</strong>`;
      if (loc.address) txt += ` — ${_esc(loc.address)}`;
      if (loc.w3w)     txt += ` <span style="color:#4cd98a">///what3words: ${_esc(loc.w3w)}</span>`;
      return txt;
    }).join('<br>');
  }
}

/* ── Coupon validation ────────────────────────────────────── */
async function applyCoupon() {
  const input   = document.getElementById('co-coupon-input');
  const msgEl   = document.getElementById('co-coupon-msg');
  const discRow = document.getElementById('co-discount-row');
  const discVal = document.getElementById('co-discount-val');
  const code    = input?.value.trim().toUpperCase();
  if (!code) return;

  const subtotal = parseFloat(
    (document.getElementById('co-subtotal')?.textContent || '0').replace('€', '')
  ) || 0;

  try {
    const res  = await fetch(`/api/coupons/validate?code=${encodeURIComponent(code)}&total=${subtotal.toFixed(2)}`);
    const data = await res.json();
    if (data.status === 'success') {
      msgEl.textContent = '✓ ' + data.message;
      msgEl.style.color = '#4cd98a';
      if (discRow) discRow.style.display = 'flex';
      if (discVal) discVal.textContent = '−€' + data.discount.toFixed(2);
      const fee = DELIVERY_FEES[_selectedDelivery] ?? 3.99;
      const totEl = document.getElementById('co-total');
      if (totEl) totEl.textContent = '€' + Math.max(0, subtotal + fee - data.discount).toFixed(2);
    } else {
      msgEl.textContent = data.message;
      msgEl.style.color = '#ff8080';
      if (discRow) discRow.style.display = 'none';
    }
  } catch {
    msgEl.textContent = 'Could not validate coupon.';
    msgEl.style.color = '#ff8080';
  }
}

/* ── Checkout form submission ─────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('checkout-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errBox = document.getElementById('checkout-error');
    errBox.style.display = 'none';
    const btn = document.getElementById('co-submit-btn');
    btn.disabled = true;
    btn.innerHTML = 'Placing order… <i data-lucide="loader"></i>';
    lucide.createIcons();

    const val = id => document.getElementById(id)?.value.trim() || '';
    const needsAddress   = (_selectedDelivery === 'producer_delivery');
    const loggedIn       = _isLoggedInCustomer() && _accountData;

    const payload = {
      first_name:      loggedIn ? (_accountData.first_name || '') : val('co-fname'),
      last_name:       loggedIn ? (_accountData.last_name  || '') : val('co-lname'),
      email:           loggedIn ? (_accountData.email      || '') : val('co-email'),
      phone:           val('co-phone'),
      address:         val('co-address'),
      town:            val('co-town'),
      eircode:         val('co-eircode'),
      coupon_code:     val('co-coupon-input').toUpperCase(),
      delivery_method: _selectedDelivery,
    };

    const alwaysRequired = loggedIn
      ? ['phone']
      : ['first_name', 'last_name', 'email', 'phone'];
    const addrRequired   = needsAddress ? ['address', 'town', 'eircode'] : [];
    for (const k of [...alwaysRequired, ...addrRequired]) {
      if (!payload[k]) {
        errBox.textContent = 'Please fill in all required fields.';
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.innerHTML = 'Place Order <i data-lucide="check"></i>';
        lucide.createIcons();
        return;
      }
    }

    try {
      const data = await _post('/api/checkout/submit', payload);
      if (data.status === 'success') {
        document.getElementById('cart-view').style.display     = 'none';
        document.getElementById('checkout-view').style.display = 'none';
        const sv = document.getElementById('checkout-success');
        sv.style.display       = 'flex';
        sv.style.flexDirection = 'column';
        const num = document.getElementById('success-order-num');
        if (num) num.textContent = 'Order reference: #' + data.order_id;
        _renderCart([]);
        lucide.createIcons();
      } else {
        errBox.textContent = data.message || 'Something went wrong. Please try again.';
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.innerHTML = 'Place Order <i data-lucide="check"></i>';
        lucide.createIcons();
      }
    } catch {
      errBox.textContent = 'Network error — please check your connection and try again.';
      errBox.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = 'Place Order <i data-lucide="check"></i>';
      lucide.createIcons();
    }
  });
});
