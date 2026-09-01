const $ = (sel) => document.querySelector(sel);
const RATE_LABEL = { FLEX: "Flexible", SEMI: "Semi-Flexible", NONREF: "Non-Refundable" };
const RATE_MULT = { FLEX: 1.0, SEMI: 0.9, NONREF: 0.8 };

const SID_KEY = "tcsa_session";
let sessionId = localStorage.getItem(SID_KEY) || null;
let hotels = [];
let lastStatuses = {};

function money(a, c = "USD") {
  return `${c} ${Number(a).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmt(text) {
  const esc = text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return esc
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/_(.+?)_/g, "<em>$1</em>")
    .replace(/\n/g, "<br>");
}

async function loadHotels() {
  const r = await fetch("/api/hotels");
  hotels = (await r.json()).hotels;
  const grid = $("#hotel-grid");
  grid.innerHTML = "";
  const sel = $("#f-hotel");
  sel.innerHTML = "";
  for (const h of hotels) {
    const card = document.createElement("div");
    card.className = "hotel-card";
    card.innerHTML = `
      <h3>${h.name}</h3>
      <div class="city">${h.city}</div>
      <div class="blurb">${h.blurb}</div>
      <div class="price">${money(h.nightly_rate)} <small>/ night, Flexible</small></div>
      <button data-hotel="${h.hotel_id}">Select</button>`;
    grid.appendChild(card);
    const opt = document.createElement("option");
    opt.value = h.hotel_id;
    opt.textContent = `${h.name} — ${h.city}`;
    sel.appendChild(opt);
  }
  updateQuote();
}

function updateQuote() {
  const hotel = hotels.find((h) => h.hotel_id === $("#f-hotel").value);
  const rate = $("#f-rate").value;
  const nights = Math.max(1, Number($("#f-nights").value) || 1);
  if (!hotel) return;
  const nightly = hotel.nightly_rate * RATE_MULT[rate];
  const room = nightly * nights;
  const total = room + room * 0.12;
  $("#quote-line").innerHTML =
    `Estimate: <strong>${money(total)}</strong> total for ${nights} night(s) ` +
    `at ${RATE_LABEL[rate]} rate (${money(nightly)}/night + 12% taxes).`;
}

$("#hotel-grid").addEventListener("click", (e) => {
  const id = e.target.dataset.hotel;
  if (!id) return;
  $("#f-hotel").value = id;
  document.getElementById("book").scrollIntoView({ behavior: "smooth" });
  updateQuote();
});

["f-hotel", "f-rate", "f-nights"].forEach((id) =>
  $("#" + id).addEventListener("input", updateQuote)
);

$("#book-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    hotel_id: $("#f-hotel").value,
    rate_plan: $("#f-rate").value,
    check_in: $("#f-checkin").value ? new Date($("#f-checkin").value + "T15:00:00Z").toISOString() : "",
    nights: Number($("#f-nights").value),
    guest_name: $("#f-guest").value,
    last_name: $("#f-last").value,
    email: $("#f-email").value,
  };
  const out = $("#book-result");
  if (!body.check_in) {
    out.innerHTML = `<span class="err">Pick a check-in date.</span>`;
    return;
  }
  const r = await fetch("/api/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (data.ok) {
    const b = data.booking;
    out.innerHTML = `<span class="ok">Booked! Reference <strong>${b.booking_id}</strong> — ` +
      `${money(b.amount_paid, b.currency)} total. Look it up under "My bookings" or ask the chat.</span>`;
    $("#lookup-email").value = b.email;
    loadMyBookings(b.email);
    refreshDev();
  } else {
    out.innerHTML = `<span class="err">Couldn't book: ${data.reason || "unknown error"}</span>`;
  }
});

async function loadMyBookings(email) {
  const list = $("#my-bookings-list");
  if (!email) { list.innerHTML = ""; return; }
  const r = await fetch("/api/bookings?email=" + encodeURIComponent(email));
  const data = await r.json();
  list.innerHTML = "";
  if (!data.bookings.length) {
    list.innerHTML = `<p style="color:var(--muted)">No bookings for that email yet.</p>`;
    return;
  }
  for (const b of data.bookings) {
    const card = document.createElement("div");
    card.className = "hotel-card booking-card";
    card.innerHTML = `
      <span class="badge ${b.status}">${b.status}</span>
      <h3>${b.booking_id}</h3>
      <div class="city">${b.hotel}</div>
      <div class="blurb">${RATE_LABEL[b.rate_plan] || b.rate_plan} · ${b.check_in.slice(0,10)} · ${b.nights} nights</div>
      <div class="price">${money(b.amount_paid, b.currency)}</div>
      ${b.status === "CANCELLED" ? `<div class="code">Refund ${money(b.refund_amount, b.currency)} · ${b.refund_code}</div>` : ""}
      <button data-ask="${b.booking_id}" data-last="${b.last_name}">Ask support about this</button>`;
    list.appendChild(card);
  }
}

$("#lookup-form").addEventListener("submit", (e) => {
  e.preventDefault();
  loadMyBookings($("#lookup-email").value.trim());
});

$("#my-bookings-list").addEventListener("click", (e) => {
  const bid = e.target.dataset.ask;
  if (!bid) return;
  openChat();
  send(`Check booking ${bid}, surname ${e.target.dataset.last}`);
});

function openChat() { $("#chat-panel").classList.remove("hidden"); }
$("#chat-fab").addEventListener("click", () => $("#chat-panel").classList.toggle("hidden"));
$("#chat-close").addEventListener("click", () => $("#chat-panel").classList.add("hidden"));

function addMessage(role, text, tools) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = fmt(text);
  if (tools && tools.length) {
    const t = document.createElement("div");
    t.className = "tools";
    t.textContent = "tools: " + tools.join(" → ");
    div.appendChild(t);
  }
  $("#messages").appendChild(div);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

async function send(message) {
  addMessage("user", message);
  $("#chat-input").value = "";
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    const data = await r.json();
    sessionId = data.session_id;
    localStorage.setItem(SID_KEY, sessionId);
    addMessage("bot", data.reply, data.tools_called);
    renderBookings(data.bookings);
    renderLogs(data.logs);
    $("#mode-badge").textContent = "agent: " + data.agent_mode;
    const email = $("#lookup-email").value.trim();
    if (email) loadMyBookings(email);
  } catch (e) {
    addMessage("bot", "⚠️ Request failed: " + e.message);
  }
}

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#chat-input").value.trim();
  if (v) send(v);
});
$("#chips").addEventListener("click", (e) => {
  if (e.target.dataset.msg) send(e.target.dataset.msg);
});

$("#dev-toggle").addEventListener("click", () => {
  $("#dev-drawer").classList.toggle("hidden");
  if (!$("#dev-drawer").classList.contains("hidden")) refreshDev();
});

function renderBookings(rows) {
  const body = $("#bookings-body");
  body.innerHTML = "";
  for (const b of rows) {
    const tr = document.createElement("tr");
    if (lastStatuses[b.booking_id] && lastStatuses[b.booking_id] !== b.status) tr.className = "flash";
    tr.innerHTML = `
      <td>${b.booking_id}</td><td>${b.guest_name}</td><td>${b.rate_plan}</td>
      <td>${money(b.amount_paid, b.currency)}</td>
      <td><span class="badge ${b.status}">${b.status}</span></td>
      <td>${b.refund_amount ? money(b.refund_amount, b.currency) : "—"}</td>`;
    body.appendChild(tr);
    lastStatuses[b.booking_id] = b.status;
  }
}

function renderLogs(logs) {
  const list = $("#log-list");
  list.innerHTML = "";
  for (const e of [...logs].reverse()) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="tool-name">${e.tool}</span><span class="dur">${e.duration_ms} ms</span>
      <div class="kv">in: ${JSON.stringify(e.params)}</div>
      <div class="kv">out: ${JSON.stringify(e.result)}</div>`;
    list.appendChild(li);
  }
}

async function refreshDev() {
  const r = await fetch("/api/bookings");
  const data = await r.json();
  renderBookings(data.bookings);
  $("#mode-badge").textContent = "agent: " + data.agent_mode;
  const lr = await fetch("/api/logs");
  renderLogs((await lr.json()).logs);
}

$("#reset-btn").addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  lastStatuses = {};
  sessionId = null;
  localStorage.removeItem(SID_KEY);
  $("#messages").innerHTML = "";
  $("#my-bookings-list").innerHTML = "";
  $("#book-result").innerHTML = "";
  addMessage("bot", "Demo data reset. Session cleared.");
  refreshDev();
});

(function init() {
  const d = new Date(Date.now() + 10 * 86400000);
  $("#f-checkin").value = d.toISOString().slice(0, 10);
  loadHotels();
  addMessage("bot", "Hi! Ask me about our cancellation policy, or give me a booking reference and surname to look it up or cancel it.");
  refreshDev();
  setInterval(refreshDev, 5000);
})();
