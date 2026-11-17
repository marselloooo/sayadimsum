const PRICE = 15000;
let quantities = {"Dimsum": 0, "Fried dimsum": 0};
let payment = "QRIS";
let toastTimer;

const rupiah = n => new Intl.NumberFormat("id-ID", {style:"currency",currency:"IDR",maximumFractionDigits:0}).format(n);
const $ = id => document.getElementById(id);

function toast(message) {
  const el = $("toast"); el.textContent = message; el.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}
function showPage(pageId) {
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === pageId));
  document.querySelectorAll(".nav-link").forEach(b => b.classList.toggle("active", b.dataset.page === pageId));
  const headings = {"order-page":"Order Input","progress-page":"In Progress","sales-page":"Daily Sales"};
  $("page-heading").textContent = headings[pageId];
}
document.querySelectorAll(".nav-link").forEach(btn => btn.addEventListener("click", () => showPage(btn.dataset.page)));

function updateOrderTotal() {
  $("qty-dimsum").textContent = quantities["Dimsum"];
  $("qty-fried").textContent = quantities["Fried dimsum"];
  $("order-total").textContent = rupiah((quantities["Dimsum"] + quantities["Fried dimsum"]) * PRICE);
}
document.querySelectorAll(".qty-btn").forEach(btn => btn.addEventListener("click", () => {
  const item = btn.dataset.item, step = Number(btn.dataset.step);
  quantities[item] = Math.max(0, quantities[item] + step);
  updateOrderTotal();
}));
document.querySelectorAll(".payment-option").forEach(btn => btn.addEventListener("click", () => {
  payment = btn.dataset.payment;
  document.querySelectorAll(".payment-option").forEach(x => x.classList.toggle("selected", x === btn));
}));

async function api(url, options={}) {
  const response = await fetch(url, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Terjadi kesalahan.");
  return data;
}

$("process-order").addEventListener("click", async () => {
  const message = $("order-message");
  try {
    const result = await api("/api/orders", {method:"POST", body:JSON.stringify({items:quantities,payment})});
    message.textContent = `Pesanan berhasil! Nomor antrean: ${result.order.queue_no}`;
    quantities = {"Dimsum":0,"Fried dimsum":0}; updateOrderTotal();
    toast(`Pesanan #${result.order.queue_no} masuk ke antrean.`);
    await refresh();
    showPage("progress-page");
  } catch(e) { message.textContent = e.message; message.style.color = "#c45b3e"; }
});

$("save-stock").addEventListener("click", async () => {
  try {
    const stock = Number($("stock-input").value);
    await api("/api/stock", {method:"POST",body:JSON.stringify({stock})});
    toast("Stok hari ini berhasil disimpan."); await refresh();
  } catch(e) { toast(e.message); }
});

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("id-ID",{hour:"2-digit",minute:"2-digit"});
}
function renderProgress(orders) {
  $("nav-count").textContent = orders.length;
  $("progress-total").textContent = orders.length;
  $("mini-progress").textContent = orders.length;
  $("progress-list").innerHTML = "";
  if (!orders.length) {
    $("progress-list").innerHTML = '<div class="panel empty-state">Belum ada pesanan dalam antrean. Pesanan baru akan muncul di sini.</div>';
    return;
  }
  orders.forEach(order => {
    const menu = Object.entries(order.items).filter(([,q])=>q>0).map(([name,q])=>`${name} x${q}`).join(" · ");
    const card = document.createElement("div"); card.className = "order-card";
    card.innerHTML = `<div class="queue-number">${order.queue_no}</div>
      <div class="order-detail"><b>Pesanan #${order.queue_no}</b><p>${menu}</p>
      <div class="order-meta"><span>${order.payment}</span><span>${rupiah(order.amount)}</span><span>${formatTime(order.created_at)}</span></div></div>
      <div class="timer" data-created="${order.created_at}">05:00</div><button class="done-btn" data-id="${order.id}">Done ✓</button>`;
    card.querySelector(".done-btn").addEventListener("click", () => markDone(order.id));
    $("progress-list").appendChild(card);
  });
}
async function markDone(id) {
  try {
    const result = await api(`/api/orders/${id}/done`, {method:"POST",body:"{}"});
    if (result.mqtt_sent) toast(`Antrean #${result.queue_no} selesai. Sinyal MQTT terkirim ke ESP32!`);
    else toast(`Pesanan selesai, tetapi MQTT gagal: ${result.mqtt_error || "cek broker"}`);
    await refresh();
  } catch(e) { toast(e.message); }
}
function updateTimers() {
  document.querySelectorAll(".timer[data-created]").forEach(el => {
    const started = new Date(el.dataset.created).getTime();
    const remaining = Math.max(0, 300 - Math.floor((Date.now() - started) / 1000));
    const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
    const ss = String(remaining % 60).padStart(2, "0");
    el.textContent = remaining > 0 ? `${mm}:${ss}` : "Siap dicek";
  });
}
function renderSales(data) {
  $("revenue").textContent = rupiah(data.revenue);
  $("sold-stock").textContent = `${data.sold_qty} / ${data.stock_today}`;
  $("menu-sold").textContent = `${data.dimsum_sold} / ${data.fried_sold}`;
  $("payment-sold").textContent = `${data.qris_count} / ${data.cash_count}`;
  $("sales-date").textContent = new Date().toLocaleDateString("id-ID",{day:"numeric",month:"short",year:"numeric"});
  const rows = data.done;
  $("sales-empty").style.display = rows.length ? "none" : "block";
  $("sales-table").innerHTML = rows.map(o => {
    const menu = Object.entries(o.items).filter(([,q])=>q>0).map(([n,q])=>`${n} x${q}`).join(", ");
    return `<tr><td>${formatTime(o.completed_at)}</td><td>#${o.queue_no}</td><td>${menu}</td><td>${o.payment}</td><td>${rupiah(o.amount)}</td></tr>`;
  }).join("");
}
async function refresh() {
  try {
    const data = await api("/api/state");
    $("stock-available").textContent = data.remaining;
    $("stock-input").value = data.stock_today;
    $("sold-today").textContent = data.sold_qty;
    $("stock-left").textContent = data.remaining;
    $("progress-stock").textContent = data.stock_today;
    $("progress-left").textContent = data.remaining;
    $("mini-done").textContent = data.done.length;
    const percent = data.stock_today ? Math.max(0, Math.min(100, data.remaining/data.stock_today*100)) : 0;
    $("stock-bar").style.width = percent + "%";
    $("stock-bar").style.background = percent < 20 ? "#d47b48" : "#368568";
    renderProgress(data.progress); updateTimers(); renderSales(data);
  } catch(e) { console.error(e); }
}
async function checkMqtt() {
  try {
    const data = await api("/api/health");
    $("mqtt-status").textContent = `Topic: ${data.mqtt_topic}`;
    $("mqtt-dot").style.background = "#d69a45";
  } catch(e) {
    $("mqtt-status").textContent = "Backend tidak terhubung";
    $("mqtt-dot").style.background = "#c75b4c";
  }
}
$("today-label").textContent = new Date().toLocaleDateString("id-ID",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
refresh(); checkMqtt(); setInterval(refresh, 5000); setInterval(updateTimers, 1000);
