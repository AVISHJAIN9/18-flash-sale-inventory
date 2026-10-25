/**
 * Live Stock Dashboard Logic (FLS-116).
 * Polls inventory gateway, calculates sell-through metrics, and simulates reservations.
 */

const API_BASE_URL = "http://localhost:8180";

// Fallback seed catalog when API is not running or initial load
const SEED_DATA = [
  { sku_id: "sku-shoe-cyber-01", product_id: "prod-cyber-shoe", total_allocated: 50, available: 32, reserved: 8, sold: 10 },
  { sku_id: "sku-gpu-titan-99", product_id: "prod-titan-gpu", total_allocated: 20, available: 4, reserved: 6, sold: 10 },
  { sku_id: "sku-phone-fold-x", product_id: "prod-fold-phone", total_allocated: 100, available: 85, reserved: 5, sold: 10 },
  { sku_id: "sku-console-ultra", product_id: "prod-ultra-console", total_allocated: 30, available: 0, reserved: 2, sold: 28 }
];

let currentInventory = [...SEED_DATA];

async function fetchInventoryFeed() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/dashboard/stock`);
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data) && data.length > 0) {
        currentInventory = data;
        document.getElementById("connection-status").textContent = "GATEWAY CONNECTED (PORT 8180)";
        document.getElementById("connection-status").style.color = "var(--accent-green)";
      }
    } else {
      document.getElementById("connection-status").textContent = "DEMO FEED (PORT 8180 STANDBY)";
      document.getElementById("connection-status").style.color = "var(--accent-amber)";
    }
  } catch (err) {
    document.getElementById("connection-status").textContent = "OFFLINE FEED (STANDALONE DEMO)";
    document.getElementById("connection-status").style.color = "var(--accent-cyan)";
  }

  renderDashboard();
  document.getElementById("last-sync-time").textContent = `Sync: ${new Date().toLocaleTimeString()}`;
}

function renderDashboard() {
  let totalAllocated = 0;
  let totalAvailable = 0;
  let totalReserved = 0;
  let totalSold = 0;

  const tbody = document.getElementById("inventory-tbody");
  tbody.innerHTML = "";

  const skuSelect = document.getElementById("sku-select");
  const selectedSku = skuSelect.value;
  skuSelect.innerHTML = '<option value="">Select SKU...</option>';

  currentInventory.forEach(item => {
    totalAllocated += item.total_allocated;
    totalAvailable += item.available;
    totalReserved += item.reserved;
    totalSold += item.sold;

    const sellThrough = item.total_allocated > 0 ? (item.sold / item.total_allocated * 100).toFixed(1) : "0.0";

    let statusClass = "instock";
    let statusText = "IN STOCK";
    if (item.available === 0 && item.reserved === 0) {
      statusClass = "soldout";
      statusText = "SOLD OUT";
    } else if (item.available <= (item.total_allocated * 0.2)) {
      statusClass = "lowstock";
      statusText = "LOW STOCK";
    }

    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="sku-tag">${item.sku_id}</span></td>
      <td>${item.product_id}</td>
      <td><strong>${item.total_allocated}</strong></td>
      <td style="color: var(--accent-green)">${item.available}</td>
      <td style="color: var(--accent-amber)">${item.reserved}</td>
      <td style="color: var(--accent-cyan)">${item.sold}</td>
      <td>
        <div style="font-size: 0.75rem; margin-bottom: 2px;">${sellThrough}%</div>
        <div class="progress-bar-mini" style="height: 4px; width: 70px;">
          <div class="progress-fill" style="width: ${sellThrough}%"></div>
        </div>
      </td>
      <td><span class="badge-status ${statusClass}">${statusText}</span></td>
    `;
    tbody.appendChild(row);

    // Option for dropdown
    const opt = document.createElement("option");
    opt.value = item.sku_id;
    opt.textContent = `${item.sku_id} (${item.available} left)`;
    if (item.sku_id === selectedSku) opt.selected = true;
    skuSelect.appendChild(opt);
  });

  // Summary Metrics
  document.getElementById("val-total").textContent = totalAllocated.toLocaleString();
  document.getElementById("val-available").textContent = totalAvailable.toLocaleString();
  document.getElementById("val-reserved").textContent = totalReserved.toLocaleString();
  document.getElementById("val-sold").textContent = totalSold.toLocaleString();

  const globalSellThrough = totalAllocated > 0 ? (totalSold / totalAllocated * 100).toFixed(1) : "0.0";
  document.getElementById("val-sellthrough").textContent = `${globalSellThrough}%`;
  document.getElementById("sellthrough-fill").style.width = `${globalSellThrough}%`;
}

// Interactive Reservation Submission
document.getElementById("reserve-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const skuId = document.getElementById("sku-select").value;
  const userId = document.getElementById("user-input").value;
  const quantity = parseInt(document.getElementById("qty-input").value, 10);
  const leaseSeconds = parseInt(document.getElementById("ttl-input").value, 10);
  const logElem = document.getElementById("log-text");

  if (!skuId) {
    logElem.textContent = "[ERROR] Please select an available SKU.";
    return;
  }

  logElem.textContent = `[HOLD_REQUEST] Submitting reservation for ${quantity}x ${skuId}...`;

  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/reservations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sku_id: skuId,
        user_id: userId,
        quantity: quantity,
        lease_seconds: leaseSeconds
      })
    });

    if (res.ok) {
      const data = await res.json();
      logElem.textContent = `[SUCCESS] Atomic reservation confirmed!\nToken: ${data.reservation.reservation_token}\nQuantity: ${data.reservation.quantity}\nExpires At: ${data.reservation.expires_at}`;
      await fetchInventoryFeed();
    } else {
      const err = await res.json();
      logElem.textContent = `[REJECTED] Hold failed: ${err.detail || "Insufficient stock or conflict"}`;
    }
  } catch (err) {
    // Local demo simulation fallback
    const target = currentInventory.find(i => i.sku_id === skuId);
    if (target && target.available >= quantity) {
      target.available -= quantity;
      target.reserved += quantity;
      logElem.textContent = `[LOCAL SIM] Simulated hold placed for ${quantity}x ${skuId}.\nToken: tok_local_${Math.random().toString(36).substr(2, 9)}\nAvailable: ${target.available}, Reserved: ${target.reserved}`;
      renderDashboard();
    } else {
      logElem.textContent = `[REJECTED] Insufficient available stock for ${skuId}!`;
    }
  }
});

document.getElementById("refresh-btn").addEventListener("click", fetchInventoryFeed);

// Auth & Session Management (FLS-026, FLS-032, FLS-038)
let activeSessionToken = null;

const loginBtn = document.getElementById("auth-login-btn");
if (loginBtn) {
  loginBtn.addEventListener("click", async () => {
    const identifier = document.getElementById("auth-username-input").value.trim();
    const password = document.getElementById("auth-password-input").value;
    const errorMsg = document.getElementById("auth-error-msg");
    const statusBadge = document.getElementById("auth-status-badge");

    errorMsg.style.display = "none";
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier, password })
      });
      if (res.ok) {
        const data = await res.json();
        activeSessionToken = data.session_token;
        statusBadge.textContent = `AUTHENTICATED (${data.user.username})`;
        statusBadge.className = "panel-badge green";
        document.getElementById("user-limit-display").textContent = `Logged in as ${data.user.username} • Limit: 2 items/SKU active`;
      } else {
        const err = await res.json();
        errorMsg.textContent = `Auth failed: ${err.detail || "Invalid credentials"}`;
        errorMsg.style.display = "block";
        statusBadge.textContent = "AUTH ERROR";
        statusBadge.className = "panel-badge red";
      }
    } catch (err) {
      statusBadge.textContent = "AUTH (OFFLINE)";
      document.getElementById("user-limit-display").textContent = `Local session simulated for ${identifier}`;
    }
  });
}

const rotateBtn = document.getElementById("auth-rotate-btn");
if (rotateBtn) {
  rotateBtn.addEventListener("click", async () => {
    if (!activeSessionToken) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/rotate`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${activeSessionToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        activeSessionToken = data.session_token;
        document.getElementById("user-limit-display").textContent = "Session rotated successfully with fresh token";
      }
    } catch (err) {
      // offline fallback
    }
  });
}

async function fetchCountersAndSummary() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/counters`);
    if (res.ok) {
      const data = await res.json();
      if (document.getElementById("val-orders-count")) {
        document.getElementById("val-orders-count").textContent = data.total_orders.toLocaleString();
      }
      if (document.getElementById("val-total-gmv")) {
        const dollars = (data.total_gmv_cents / 100).toFixed(2);
        document.getElementById("val-total-gmv").textContent = `$${dollars}`;
      }
      if (document.getElementById("val-waiting-room")) {
        document.getElementById("val-waiting-room").textContent = data.waiting_room_active.toString();
      }
    }
    const sumRes = await fetch(`${API_BASE_URL}/api/v1/dashboard/summary`);
    if (sumRes.ok) {
      const sData = await sumRes.json();
      if (document.getElementById("val-campaigns-count")) {
        document.getElementById("val-campaigns-count").textContent = sData.total_campaigns.toString();
      }
    }
  } catch (err) {
    // offline graceful fallback
  }
}

async function fetchOrders() {
  const tbody = document.getElementById("order-monitoring-tbody");
  if (!tbody) return;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/orders`);
    if (res.ok) {
      const orders = await res.json();
      if (orders.length > 0) {
        tbody.innerHTML = "";
        orders.slice(0, 20).forEach(o => {
          const tr = document.createElement("tr");
          const totalDollars = (o.total_amount_cents / 100).toFixed(2);
          const timeStr = o.created_at ? new Date(o.created_at).toLocaleTimeString() : "just now";
          tr.innerHTML = `
            <td><span class="sku-tag">${o.order_id.slice(0, 12)}...</span></td>
            <td>${o.user_id}</td>
            <td>${o.sku_id}</td>
            <td>${o.quantity}</td>
            <td>$${totalDollars}</td>
            <td><span class="badge-status instock">${o.status}</span></td>
            <td style="font-size: 0.8rem; color: var(--text-muted);">${timeStr}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }
  } catch (err) {
    // offline graceful fallback
  }
}

async function fetchAlerts() {
  const container = document.getElementById("alerts-list");
  const badge = document.getElementById("alerts-count-badge");
  if (!container) return;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/alerts`);
    if (res.ok) {
      const alerts = await res.json();
      if (badge) badge.textContent = `${alerts.length} ALERTS`;
      if (alerts.length > 0) {
        container.innerHTML = "";
        alerts.forEach(a => {
          const div = document.createElement("div");
          div.className = "alert-item";
          div.style.padding = "6px 10px";
          div.style.marginBottom = "6px";
          div.style.borderRadius = "4px";
          div.style.background = a.alert_level === "CRITICAL" ? "rgba(239, 68, 68, 0.15)" : "rgba(245, 158, 11, 0.15)";
          div.style.borderLeft = a.alert_level === "CRITICAL" ? "3px solid var(--accent-red)" : "3px solid var(--accent-amber)";
          div.innerHTML = `
            <strong style="font-size: 0.8rem;">[${a.alert_level}] ${a.sku_id}</strong>: 
            <span style="font-size: 0.8rem;">${a.available} left of ${a.total_allocated} (${a.remaining_pct}%)</span>
          `;
          container.appendChild(div);
        });
      } else {
        container.innerHTML = `<div class="alert-empty" style="color: var(--text-muted); font-size: 0.85rem;">All SKU inventory levels are within normal operating margins.</div>`;
      }
    }
  } catch (err) {
    // offline graceful fallback
  }
}

async function refreshAllFeeds() {
  await fetchInventoryFeed();
  await fetchCountersAndSummary();
  await fetchOrders();
  await fetchAlerts();
}

// Initial Load & 3-second auto-refresh
refreshAllFeeds();
setInterval(refreshAllFeeds, 3000);


