import {init as initFormatting} from "./formatting.js";

export function initProducerDashboard(productsUrl, ordersUrl, transactionsUrl, username) {
    initFormatting();

    // ── Tab switching ─────────────────────────────────────────────
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    if (tabButtons.length > 0) {
        tabButtons[0].classList.add('active');
        const firstTab = document.querySelector(tabButtons[0].dataset.tab);
        if (firstTab) firstTab.classList.add('active');
    }

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const target = document.querySelector(button.dataset.tab);
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            button.classList.add('active');
            if (target) target.classList.add('active');
        });
    });

    // ── Stat counter helper ───────────────────────────────────────
    function updateStat(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    // ── Status badge helper ───────────────────────────────────────
    function statusBadge(status) {
        const s = (status || '').toLowerCase();
        const cls = s.includes('complet') ? 'status-completed'
                  : s.includes('cancel')  ? 'status-cancelled'
                  : 'status-pending';
        return `<span class="status-badge ${cls}">${status || '—'}</span>`;
    }

    // ── Generic fetch + populate ──────────────────────────────────
    async function fetchAndPopulate(url, tableBodyId, rowBuilder, filterFn = null, postFn = null) {
        const tableBody = document.querySelector(`${tableBodyId} tbody`);
        if (!tableBody) return;

        tableBody.style.opacity = '0.5';

        try {
            const response = await fetch(url + "?v=" + new Date().getTime());
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            let data = await response.json();
            if (filterFn) data = filterFn(data);

            tableBody.innerHTML = '';
            data.forEach(item => {
                tableBody.insertAdjacentHTML('beforeend', rowBuilder(item));
            });

            attachStockUpdateListeners();
            if (postFn) postFn(data);

        } catch (error) {
            console.error(`Error loading data from ${url}:`, error);
            tableBody.innerHTML = '<tr><td colspan="100%" style="text-align:center;opacity:0.6;">Error loading data.</td></tr>';
        } finally {
            tableBody.style.opacity = '1';
        }
    }

    // ── Products ──────────────────────────────────────────────────
    function stockIndicator(stock) {
        if (stock <= 0) return '<span class="stock-indicator stock-empty">● Out of stock</span>';
        if (stock <= 5)  return '<span class="stock-indicator stock-low">● Low stock</span>';
        return '<span class="stock-indicator stock-ok">● In stock</span>';
    }

    const DELIVERY_OPTS = [
        { key: 'collect_in_person', label: 'In-Person' },
        { key: 'market_pickup',     label: 'Market' },
        { key: 'dropoff_box',       label: 'Drop-Off Box' },
        { key: 'producer_delivery', label: 'Delivery' },
    ];

    const productRowBuilder = (p) => {
        const dm = p.delivery_methods || [];
        const checksHtml = DELIVERY_OPTS.map(o => `
            <label style="display:flex;align-items:center;gap:5px;font-size:0.75rem;cursor:pointer;white-space:nowrap;margin:0;">
                <input type="checkbox" class="delivery-check" data-product-id="${p.id}" data-method="${o.key}"
                       ${dm.includes(o.key) ? 'checked' : ''} style="accent-color:#1bc467;cursor:pointer;">
                ${o.label}
            </label>
        `).join('');
        return `<tr>
            <td><img src="${p.image && p.image.startsWith('http') ? p.image : '/static/' + (p.image || '')}" alt="${p.name}" class="product-thumb" onerror="this.style.display='none'"></td>
            <td>${p.name}</td>
            <td>
                <input type="number" class="stock-input" data-id="${p.id}" value="${p.stock}" min="0">
                ${stockIndicator(p.stock)}
            </td>
            <td>
                <div style="display:flex;flex-direction:column;gap:5px;">${checksHtml}</div>
                <div class="delivery-save-msg" data-product-id="${p.id}" style="font-size:0.72rem;min-height:14px;margin-top:4px;"></div>
            </td>
        </tr>`;
    };

    function attachStockUpdateListeners() {
        // Delivery method checkboxes — save on change with short debounce per product
        const deliveryTimers = {};
        document.querySelectorAll('.delivery-check').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                const pid = checkbox.dataset.productId;
                clearTimeout(deliveryTimers[pid]);
                deliveryTimers[pid] = setTimeout(async () => {
                    const methods = [...document.querySelectorAll(`.delivery-check[data-product-id="${pid}"]:checked`)]
                        .map(c => c.dataset.method);
                    const msgEl = document.querySelector(`.delivery-save-msg[data-product-id="${pid}"]`);
                    try {
                        const csrf = document.querySelector('meta[name="csrf-token"]')?.content ?? '';
                        const res = await fetch('/api/producer/product-delivery', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                            body: JSON.stringify({ product_id: parseInt(pid), delivery_methods: methods }),
                        });
                        const data = await res.json();
                        if (msgEl) {
                            msgEl.textContent = data.status === 'success' ? '✓ Saved' : '✗ Error';
                            msgEl.style.color  = data.status === 'success' ? '#4cd98a' : '#ff8080';
                            setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 2500);
                        }
                    } catch { if (msgEl) { msgEl.textContent = '✗ Error'; msgEl.style.color = '#ff8080'; } }
                }, 600);
            });
        });

        document.querySelectorAll('.stock-input').forEach(input => {
            input.onblur = async () => {
                const productId = input.dataset.id;
                const newStock = input.value;

                try {
                    const response = await fetch('/api/products/update-stock', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content ?? ''
                        },
                        body: JSON.stringify({ id: productId, stock: newStock })
                    });

                    if (!response.ok) {
                        const err = await response.json();
                        alert("Failed to update stock: " + err.message);
                        refreshProducts();
                    } else {
                        // Update indicator in-place without a full refresh
                        const indicator = input.nextElementSibling;
                        if (indicator) indicator.outerHTML = stockIndicator(parseInt(newStock));
                    }
                } catch (error) {
                    console.error("Error updating stock:", error);
                    alert("An error occurred while updating stock.");
                    refreshProducts();
                }
            };
        });
    }

    const refreshProducts = () => fetchAndPopulate(
        productsUrl, '#product-table', productRowBuilder,
        (data) => data.filter(p => p.producer === username),
        (data) => updateStat('stat-products', data.length)
    );
    document.getElementById('refresh-products')?.addEventListener('click', refreshProducts);
    refreshProducts();
    setInterval(refreshProducts, 60000);

    // ── Modal ─────────────────────────────────────────────────────
    const modal   = document.getElementById("addProductModal");
    const openBtn = document.getElementById("open-add-product");
    const closeBtn = document.querySelector(".close-modal");
    const form    = document.getElementById("add-product-form");

    if (openBtn && modal) openBtn.onclick = () => modal.style.display = "block";
    if (closeBtn && modal) closeBtn.onclick = () => modal.style.display = "none";
    window.addEventListener('click', (e) => { if (e.target === modal) modal.style.display = "none"; });

    if (form) {
        form.onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const imageFile = formData.get('image');

            if (imageFile && imageFile.size > 5 * 1024 * 1024) {
                alert("Error: File is too large. Maximum size is 5MB.");
                return;
            }

            try {
                const response = await fetch('/api/products/add', { method: 'POST', body: formData });
                const result = await response.json();
                if (response.ok) {
                    alert(result.message);
                    modal.style.display = "none";
                    form.reset();
                    refreshProducts();
                } else {
                    alert("Error: " + result.message);
                }
            } catch (error) {
                console.error("Error creating product:", error);
                alert("An error occurred while creating the product.");
            }
        };
    }

    // ── Orders ────────────────────────────────────────────────────
    const orderRowBuilder = (o) => `<tr>
        <td>${o.id}</td>
        <td>${o.customer}</td>
        <td>${o.date}</td>
        <td>${o.total}</td>
        <td>${statusBadge(o.status)}</td>
    </tr>`;

    const refreshOrders = () => fetchAndPopulate(
        ordersUrl, '#order-table', orderRowBuilder,
        null,
        (data) => updateStat('stat-orders', data.length)
    );
    document.getElementById('refresh-orders')?.addEventListener('click', refreshOrders);
    refreshOrders();
    setInterval(refreshOrders, 60000);

    // ── Transactions ──────────────────────────────────────────────
    const transactionRowBuilder = (t) => `<tr>
        <td>${t.id}</td>
        <td>${t.date}</td>
        <td>${t.type}</td>
        <td>${t.amount}</td>
        <td>${statusBadge(t.status)}</td>
    </tr>`;

    const refreshTransactions = () => fetchAndPopulate(
        transactionsUrl, '#transaction-table', transactionRowBuilder,
        null,
        (data) => {
            updateStat('stat-transactions', data.length);
            const revenue = data
                .filter(t => (t.status || '').toLowerCase().includes('complet'))
                .reduce((sum, t) => {
                    const amt = parseFloat(String(t.amount).replace(/[^0-9.]/g, ''));
                    return sum + (isNaN(amt) ? 0 : amt);
                }, 0);
            updateStat('stat-revenue', '€' + revenue.toFixed(2));
        }
    );
    document.getElementById('refresh-transactions')?.addEventListener('click', refreshTransactions);
    refreshTransactions();
    setInterval(refreshTransactions, 60000);
}
