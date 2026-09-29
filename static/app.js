const TITLES = {
  dashboard: ["Tableau de bord", "Heures, clients et factures en un coup d'oeil"],
  temps: ["Temps", "Chronometre et saisie manuelle des heures"],
  clients: ["Clients", "Coordonnees, tarifs et taux de TVA"],
  factures: ["Factures", "Creer et telecharger les factures PDF"],
  parametres: ["Parametres", "Informations de votre societe"],
};

let state = {
  view: "dashboard",
  clients: [],
  entries: [],
  invoices: [],
  settings: {},
  timer: { running: false, elapsed_seconds: 0 },
  dash: null,
};

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return [...document.querySelectorAll(sel)]; }

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Erreur serveur");
  return data;
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2800);
}

function sansTva() {
  const s = state.settings || {};
  return String(s.billing_tva || "").toLowerCase() === "sans" || s.tva_franchise === "1";
}

function money(n) {
  return new Intl.NumberFormat("de-CH", { style: "currency", currency: "CHF" }).format(n || 0);
}
function hours(min) {
  return ((min || 0) / 60).toFixed(2).replace(".", ",") + " h";
}
function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d + "/" + m + "/" + y;
}
function statusLabel(s) {
  return { brouillon: "Brouillon", emise: "Emise", payee: "Payee" }[s] || s;
}
function statusClass(s) {
  return { brouillon: "muted", emise: "warn", payee: "ok" }[s] || "";
}
function hhmmss(sec) {
  const s = Math.max(0, sec | 0);
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const r = String(s % 60).padStart(2, "0");
  return h + ":" + m + ":" + r;
}

function openModal(html) {
  $("#modalCard").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

$all(".nav").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

function showView(name) {
  state.view = name;
  $all(".nav").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $all(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + name).classList.remove("hidden");
  const pair = TITLES[name];
  $("#pageTitle").textContent = pair[0];
  $("#pageSubtitle").textContent = pair[1];
  if (name === "dashboard") renderDashboard();
  if (name === "temps") renderTemps();
  if (name === "clients") renderClients();
  if (name === "factures") renderFactures();
  if (name === "parametres") renderSettings();
}

async function refreshAll() {
  const [dash, clients, entries, invoices] = await Promise.all([
    api("/api/dashboard"),
    api("/api/clients"),
    api("/api/entries"),
    api("/api/invoices"),
  ]);
  state.dash = dash;
  state.clients = clients;
  state.entries = entries;
  state.invoices = invoices;
  state.settings = dash.settings || {};
  state.timer = dash.timer || state.timer;
  updateTimerUi();
  showView(state.view);
}

function updateTimerUi() {
  const t = state.timer || {};
  $("#timerDisplay").textContent = hhmmss(t.elapsed_seconds || 0);
  $("#timerClient").textContent = t.running
    ? ((t.client_name || "Client") + " — " + (t.description || "En cours"))
    : "Arrete";
}

setInterval(() => {
  if (state.timer && state.timer.running) {
    state.timer.elapsed_seconds = (state.timer.elapsed_seconds || 0) + 1;
    updateTimerUi();
    const live = $("#liveTimer");
    if (live) live.textContent = hhmmss(state.timer.elapsed_seconds);
  }
}, 1000);

function clientOptions(selected) {
  return state.clients.map((c) =>
    "<option value=\"" + c.id + "\"" + (String(c.id) === String(selected) ? " selected" : "") + ">" + esc(c.name) + "</option>"
  ).join("");
}
function esc(s) {
  const map = {
    "&": String.fromCharCode(38) + "amp;",
    "<": String.fromCharCode(38) + "lt;",
    ">": String.fromCharCode(38) + "gt;",
    '"': String.fromCharCode(38) + "quot;",
    "'": String.fromCharCode(38) + "#39;"
  };
  return String(s ?? "").replace(/[&<>"']/g, (c) => map[c]);
}

function renderDashboard() {
  const d = state.dash || {};
  const amountLabel = sansTva() ? "Montant non facture" : "Montant HT non facture";
  $("#view-dashboard").innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">Cette semaine</div><div class="value">${hours(d.week_minutes)}</div></div>
      <div class="card"><div class="label">Ce mois-ci</div><div class="value">${hours(d.month_minutes)}</div></div>
      <div class="card"><div class="label">Heures a facturer</div><div class="value">${hours(d.unbilled_minutes)}</div></div>
      <div class="card"><div class="label">${amountLabel}</div><div class="value">${money(d.unbilled_amount_ht)}</div></div>
    </div>
    <div class="timer-box">
      <div class="card">
        <h2>Dernieres saisies</h2>
        ${tableEntries(d.recent_entries || [], false)}
      </div>
      <div class="card">
        <h2>A retenir</h2>
        <p>${d.clients_count || 0} client(s)</p>
        <p>${d.invoices_brouillon || 0} facture(s) brouillon</p>
        <p>${d.invoices_emises || 0} facture(s) emise(s)</p>
        <p class="muted">${sansTva() ? "Facturation sans TVA." : "Facturation avec TVA."}</p>
      </div>
    </div>
  `;
}

function tableEntries(list, actions = true) {
  if (!list.length) return `<div class="empty">Aucune heure enregistree.</div>`;
  const amountHead = sansTva() ? "Montant" : "Montant HT";
  return `<table>
    <thead><tr>
      <th>Date</th><th>Client</th><th>Designation</th><th>Duree</th><th>${amountHead}</th>
      ${actions ? "<th></th>" : ""}
    </tr></thead>
    <tbody>
      ${list.map((e) => `<tr>
        <td>${fmtDate(e.work_date)}</td>
        <td>${esc(e.client_name)}</td>
        <td>${esc(e.description)}</td>
        <td>${hours(e.duration_minutes)}</td>
        <td>${money(e.amount_ht)}</td>
        ${actions ? `<td class="actions">
          ${e.invoice_id ? `<span class="badge">Facturee</span>` : `
            <button class="btn small secondary" onclick="editEntry(${e.id})">Modifier</button>
            <button class="btn small danger" onclick="removeEntry(${e.id})">Supprimer</button>
          `}
        </td>` : ""}
      </tr>`).join("")}
    </tbody>
  </table>`;
}

function renderTemps() {
  const t = state.timer || {};
  $("#view-temps").innerHTML = `
    <div class="timer-box">
      <div class="card">
        <h2>Chronometre</h2>
        <div class="timer-display" id="liveTimer">${hhmmss(t.elapsed_seconds || 0)}</div>
        <div class="form-grid" style="margin-top:12px">
          <div>
            <label>Client</label>
            <select id="timerClientId">${clientOptions(t.client_id)}</select>
          </div>
          <div>
            <label>Designation</label>
            <input id="timerDesc" value="${esc(t.description || "")}" placeholder="Comptabilite, reunion..." />
          </div>
        </div>
        <div class="row" style="margin-top:12px">
          ${t.running
            ? `<button class="btn accent" onclick="stopTimer()">Arreter et enregistrer</button>
               <button class="btn secondary" onclick="cancelTimer()">Annuler</button>`
            : `<button class="btn" onclick="startTimer()">Demarrer</button>`}
        </div>
      </div>
      <div class="card">
        <h2>Saisie manuelle</h2>
        <div class="form-grid">
          <div><label>Client</label><select id="manClient">${clientOptions()}</select></div>
          <div><label>Date</label><input type="date" id="manDate" /></div>
          <div class="full"><label>Designation</label><input id="manDesc" placeholder="Prestation realisee" /></div>
          <div><label>Heures</label><input id="manHours" type="number" min="0.25" step="0.25" value="1" /></div>
          <div><label>Tarif (CHF / h)</label><input id="manRate" type="number" step="0.01" placeholder="tarif du client" /></div>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn" onclick="addManual()">Enregistrer</button>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="toolbar">
        <h2>Historique</h2>
        <button class="btn secondary" onclick="showView('factures')">Creer une facture</button>
      </div>
      ${tableEntries(state.entries)}
    </div>
  `;
  const today = new Date().toISOString().slice(0, 10);
  const dateEl = $("#manDate");
  if (dateEl) dateEl.value = today;
}

async function startTimer() {
  try {
    state.timer = await api("/api/timer/start", {
      method: "POST",
      body: { client_id: $("#timerClientId").value, description: $("#timerDesc").value },
    });
    toast("Chronometre demarre");
    renderTemps();
    updateTimerUi();
  } catch (e) { toast(e.message); }
}
async function stopTimer() {
  try {
    const data = await api("/api/timer/stop", { method: "POST" });
    state.timer = data.timer;
    toast("Temps enregistre");
    await refreshAll();
  } catch (e) { toast(e.message); }
}
async function cancelTimer() {
  state.timer = await api("/api/timer/cancel", { method: "POST" });
  toast("Chronometre annule");
  renderTemps();
  updateTimerUi();
}
async function addManual() {
  try {
    await api("/api/entries", {
      method: "POST",
      body: {
        client_id: $("#manClient").value,
        work_date: $("#manDate").value,
        description: $("#manDesc").value,
        hours: $("#manHours").value,
        hourly_rate_ht: $("#manRate").value,
      },
    });
    toast("Heure enregistree");
    await refreshAll();
  } catch (e) { toast(e.message); }
}
async function removeEntry(id) {
  if (!confirm("Supprimer cette saisie ?")) return;
  try {
    await api("/api/entries/" + id, { method: "DELETE" });
    await refreshAll();
  } catch (e) { toast(e.message); }
}
function editEntry(id) {
  const e = state.entries.find((x) => x.id === id);
  if (!e) return;
  openModal(`
    <h2>Modifier la saisie</h2>
    <div class="form-grid">
      <div><label>Client</label><select id="edClient">${clientOptions(e.client_id)}</select></div>
      <div><label>Date</label><input type="date" id="edDate" value="${e.work_date}" /></div>
      <div class="full"><label>Designation</label><input id="edDesc" value="${esc(e.description)}" /></div>
      <div><label>Heures</label><input id="edHours" type="number" step="0.25" value="${e.hours}" /></div>
      <div><label>Tarif</label><input id="edRate" type="number" step="0.01" value="${e.hourly_rate_ht}" /></div>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="btn" onclick="saveEntry(${id})">Enregistrer</button>
      <button class="btn secondary" onclick="closeModal()">Annuler</button>
    </div>
  `);
}
async function saveEntry(id) {
  try {
    await api("/api/entries/" + id, {
      method: "PUT",
      body: {
        client_id: $("#edClient").value,
        work_date: $("#edDate").value,
        description: $("#edDesc").value,
        hours: $("#edHours").value,
        hourly_rate_ht: $("#edRate").value,
      },
    });
    closeModal();
    await refreshAll();
  } catch (e) { toast(e.message); }
}

function renderClients() {
  $("#view-clients").innerHTML = `
    <div class="toolbar">
      <div>
        <h2>${state.clients.length} client(s) enregistre(s)</h2>
        <p class="muted">Chaque client a son tarif horaire. Le temps saisi utilise ce prix pour calculer la facture.</p>
      </div>
      <button class="btn" onclick="editClient()">Nouveau client</button>
    </div>
    <div class="card">
      ${!state.clients.length ? `<div class="empty">Aucun client dans la base.</div>` : `
      <table>
        <thead><tr><th>Nom</th><th>Coordonnees</th><th>Contact</th><th>Tarif / h</th>${sansTva() ? "" : "<th>TVA</th>"}<th>A facturer</th><th></th></tr></thead>
        <tbody>
          ${state.clients.map((c) => `<tr>
            <td><strong>${esc(c.name)}</strong></td>
            <td>${esc([c.address, [c.postal_code, c.city].filter(Boolean).join(" "), c.country].filter(Boolean).join(" · "))}</td>
            <td>${esc([c.email, c.phone].filter(Boolean).join(" · "))}</td>
            <td>${money(c.hourly_rate_ht)}</td>
            ${sansTva() ? "" : `<td>${c.tva_rate} %</td>`}
            <td>${hours(c.unbilled_minutes)}</td>
            <td class="actions">
              <button class="btn small secondary" onclick="editClient(${c.id})">Fiche</button>
              <button class="btn small danger" onclick="removeClient(${c.id})">Supprimer</button>
            </td>
          </tr>`).join("")}
        </tbody>
      </table>`}
    </div>
  `;
}

function editClient(id) {
  const c = state.clients.find((x) => x.id === id) || {
    name: "", address: "", postal_code: "", city: "", country: "Suisse",
    email: "", phone: "", siret: "", tva_intra: "",
    hourly_rate_ht: state.settings.default_hourly_rate || 50,
    tva_rate: sansTva() ? 0 : (state.settings.default_tva_rate || 8.1), notes: ""
  };
  openModal(`
    <h2>${id ? "Modifier le client" : "Nouveau client"}</h2>
    <div class="form-grid">
      <div class="full"><label>Nom / societe</label><input id="cName" value="${esc(c.name)}" /></div>
      <div class="full"><label>Adresse</label><input id="cAddress" value="${esc(c.address)}" /></div>
      <div><label>Code postal</label><input id="cCP" value="${esc(c.postal_code)}" /></div>
      <div><label>Ville</label><input id="cCity" value="${esc(c.city)}" /></div>
      <div><label>Pays</label><input id="cCountry" value="${esc(c.country)}" /></div>
      <div><label>E-mail</label><input id="cEmail" value="${esc(c.email)}" /></div>
      <div><label>Telephone</label><input id="cPhone" value="${esc(c.phone)}" /></div>
      <div><label>N IDE / SIRET</label><input id="cSiret" value="${esc(c.siret)}" /></div>
      <div><label>N TVA</label><input id="cTvaId" value="${esc(c.tva_intra)}" /></div>
      <div><label>Tarif horaire (CHF)</label><input id="cRate" type="number" step="0.01" value="${c.hourly_rate_ht}" /></div>
      ${sansTva() ? "" : `<div><label>Taux de TVA (%)</label><input id="cTva" type="number" step="0.1" value="${c.tva_rate}" /></div>`}
      <div class="full"><label>Notes</label><textarea id="cNotes">${esc(c.notes)}</textarea></div>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="btn" onclick="saveClient(${id || "null"})">Enregistrer</button>
      <button class="btn secondary" onclick="closeModal()">Annuler</button>
    </div>
  `);
}
async function saveClient(id) {
  const body = {
    name: $("#cName").value,
    address: $("#cAddress").value,
    postal_code: $("#cCP").value,
    city: $("#cCity").value,
    country: $("#cCountry").value,
    email: $("#cEmail").value,
    phone: $("#cPhone").value,
    siret: $("#cSiret").value,
    tva_intra: $("#cTvaId").value,
    hourly_rate_ht: $("#cRate").value,
    tva_rate: $("#cTva") ? $("#cTva").value : 0,
    notes: $("#cNotes").value,
  };
  if (!body.name.trim()) return toast("Le nom est obligatoire");
  try {
    if (id) await api("/api/clients/" + id, { method: "PUT", body });
    else await api("/api/clients", { method: "POST", body });
    closeModal();
    await refreshAll();
  } catch (e) { toast(e.message); }
}
async function removeClient(id) {
  if (!confirm("Supprimer ce client et ses heures non facturees ?")) return;
  try {
    await api("/api/clients/" + id, { method: "DELETE" });
    await refreshAll();
  } catch (e) { toast(e.message); }
}

function renderFactures() {
  $("#view-factures").innerHTML = `
    <div class="toolbar">
      <h2>${state.invoices.length} facture(s)</h2>
      <button class="btn accent" onclick="newInvoice()">Nouvelle facture</button>
    </div>
    <div class="card">
      ${!state.invoices.length ? `<div class="empty">Aucune facture pour le moment.</div>` : `
      <table>
        <thead><tr><th>N</th><th>Client</th><th>Date</th><th>Echeance</th><th>Total</th><th>Statut</th><th></th></tr></thead>
        <tbody>
          ${state.invoices.map((i) => `<tr>
            <td>${esc(i.number)}</td>
            <td>${esc(i.client_name)}</td>
            <td>${fmtDate(i.issue_date)}</td>
            <td>${fmtDate(i.due_date)}</td>
            <td>${money(i.apply_tva ? i.total_ttc : i.total_ht)}</td>
            <td><span class="badge ${statusClass(i.status)}">${statusLabel(i.status)}</span></td>
            <td class="actions">
              <a class="btn small secondary" href="/api/invoices/${i.id}/pdf" target="_blank">PDF</a>
              ${i.status !== "emise" && i.status !== "payee" ? `<button class="btn small" onclick="setStatus(${i.id}, 'emise')">Emettre</button>` : ""}
              ${i.status !== "payee" ? `<button class="btn small" onclick="setStatus(${i.id}, 'payee')">Payee</button>` : ""}
              ${i.status !== "payee" ? `<button class="btn small danger" onclick="removeInvoice(${i.id})">Supprimer</button>` : ""}
            </td>
          </tr>`).join("")}
        </tbody>
      </table>`}
    </div>
  `;
}

function newInvoice() {
  const unbilled = state.entries.filter((e) => e.billable && !e.invoice_id);
  const byClient = {};
  unbilled.forEach((e) => {
    byClient[e.client_id] = byClient[e.client_id] || [];
    byClient[e.client_id].push(e);
  });
  const options = Object.keys(byClient).map((id) => {
    const name = state.clients.find((c) => String(c.id) === String(id))?.name || id;
    return "<option value=\"" + id + "\">" + esc(name) + " (" + byClient[id].length + " saisie(s))</option>";
  }).join("");
  const defaultSans = sansTva();
  openModal(`
    <h2>Nouvelle facture</h2>
    ${!options ? `<p class="notice">Aucune heure a facturer. Enregistrez d'abord du temps.</p>
      <button class="btn secondary" onclick="closeModal()">Fermer</button>` : `
    <div class="form-grid">
      <div class="full"><label>Client</label><select id="invClient">${options}</select></div>
      <div><label>Date d'emission</label><input type="date" id="invIssue" /></div>
      <div><label>Date d'echeance</label><input type="date" id="invDue" /></div>
      <div class="full">
        <label>TVA</label>
        <select id="invTva">
          <option value="sans" ${defaultSans ? "selected" : ""}>Sans TVA</option>
          <option value="avec" ${defaultSans ? "" : "selected"}>Avec TVA</option>
        </select>
      </div>
      <div class="full"><label>Notes visibles sur la facture</label><textarea id="invNotes"></textarea></div>
    </div>
    <p class="muted">Toutes les heures non facturees de ce client seront incluses.</p>
    <div id="invLines"></div>
    <div class="row" style="margin-top:14px">
      <button class="btn accent" onclick="createInvoice()">Creer la facture</button>
      <button class="btn secondary" onclick="closeModal()">Annuler</button>
    </div>`}
  `);
  if (options) {
    const today = new Date();
    $("#invIssue").value = today.toISOString().slice(0, 10);
    const due = new Date(today);
    due.setDate(due.getDate() + parseInt(state.settings.payment_days || "30", 10));
    $("#invDue").value = due.toISOString().slice(0, 10);
    const refreshLines = () => {
      const id = $("#invClient").value;
      const list = byClient[id] || [];
      const total = list.reduce((s, e) => s + e.amount_ht, 0);
      $("#invLines").innerHTML = `<div class="check-list">
        ${list.map((e) => `<label>
          <input type="checkbox" class="invEntry" value="${e.id}" checked />
          ${fmtDate(e.work_date)} — ${esc(e.description) || "Prestation"} — ${hours(e.duration_minutes)} — ${money(e.amount_ht)}
        </label>`).join("")}
      </div><p>Total selectionnable : <strong>${money(total)}</strong></p>`;
    };
    $("#invClient").addEventListener("change", refreshLines);
    refreshLines();
  }
}

async function createInvoice() {
  const ids = $all(".invEntry:checked").map((x) => parseInt(x.value, 10));
  try {
    const inv = await api("/api/invoices", {
      method: "POST",
      body: {
        client_id: $("#invClient").value,
        issue_date: $("#invIssue").value,
        due_date: $("#invDue").value,
        notes: $("#invNotes").value,
        entry_ids: ids,
        apply_tva: $("#invTva").value === "avec" ? 1 : 0,
      },
    });
    closeModal();
    toast("Facture " + inv.number + " creee");
    await refreshAll();
    window.open("/api/invoices/" + inv.id + "/pdf", "_blank");
  } catch (e) { toast(e.message); }
}
async function setStatus(id, status) {
  try {
    await api("/api/invoices/" + id + "/status", { method: "POST", body: { status } });
    await refreshAll();
  } catch (e) { toast(e.message); }
}
async function removeInvoice(id) {
  if (!confirm("Supprimer cette facture ? Les heures redeviendront disponibles.")) return;
  try {
    await api("/api/invoices/" + id, { method: "DELETE" });
    await refreshAll();
  } catch (e) { toast(e.message); }
}

function renderSettings() {
  const s = state.settings || {};
  const mode = sansTva() ? "sans" : "avec";
  $("#view-parametres").innerHTML = `
    <div class="card">
      <h2>Connexion telephone / Android</h2>
      <p class="muted">Le PC et le telephone partagent la meme base. Lancez <strong>lancer-reseau.bat</strong> sur Windows, puis ouvrez l'adresse ci-dessous dans Chrome sur le telephone. Menu > Ajouter a l'ecran d'accueil.</p>
      <div id="netInfo" class="notice">Recherche de l'adresse reseau...</div>
      <div class="form-grid" style="margin-top:12px">
        <div class="full">
          <label>Mot de passe serveur (pour Internet / Android)</label>
          <input id="sAccess" type="password" placeholder="laissez vide en local" />
        </div>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn secondary" type="button" onclick="logoutServer()">Se deconnecter</button>
      </div>
    </div>
    <div class="card">
      <h2>Votre societe (emetteur des factures)</h2>
      <div class="form-grid">
        <div><label>Raison sociale</label><input id="sName" value="${esc(s.company_name)}" /></div>
        <div><label>Forme juridique</label><input id="sForm" value="${esc(s.company_legal_form)}" /></div>
        <div class="full"><label>Adresse</label><input id="sAddress" value="${esc(s.company_address)}" /></div>
        <div><label>Code postal</label><input id="sCP" value="${esc(s.company_postal_code)}" /></div>
        <div><label>Ville</label><input id="sCity" value="${esc(s.company_city)}" /></div>
        <div><label>Pays</label><input id="sCountry" value="${esc(s.company_country)}" /></div>
        <div><label>E-mail</label><input id="sEmail" value="${esc(s.company_email)}" /></div>
        <div><label>Telephone</label><input id="sPhone" value="${esc(s.company_phone)}" /></div>
        <div><label>N IDE / SIRET</label><input id="sSiret" value="${esc(s.company_siret)}" /></div>
        <div><label>N TVA</label><input id="sTva" value="${esc(s.company_tva)}" /></div>
        <div><label>IBAN</label><input id="sIban" value="${esc(s.company_iban)}" /></div>
        <div><label>BIC</label><input id="sBic" value="${esc(s.company_bic)}" /></div>
        <div><label>Delai de paiement (jours)</label><input id="sDays" type="number" value="${esc(s.payment_days)}" /></div>
        <div><label>Prefixe des factures</label><input id="sPrefix" value="${esc(s.invoice_prefix)}" /></div>
        <div><label>Tarif horaire par defaut (CHF)</label><input id="sRate" type="number" step="0.01" value="${esc(s.default_hourly_rate)}" /></div>
        <div><label>TVA par defaut (%)</label><input id="sTvaRate" type="number" step="0.1" value="${esc(s.default_tva_rate)}" /></div>
        <div class="full">
          <label>Facturation</label>
          <select id="sBillingTva">
            <option value="sans" ${mode === "sans" ? "selected" : ""}>Sans TVA</option>
            <option value="avec" ${mode === "avec" ? "selected" : ""}>Avec TVA</option>
          </select>
        </div>
        <div class="full"><label>Mentions de bas de facture</label><textarea id="sFooter" rows="4">${esc(s.invoice_footer)}</textarea></div>
      </div>
      <div class="row" style="margin-top:14px">
        <button class="btn" onclick="saveSettings()">Enregistrer les parametres</button>
      </div>
    </div>
  `;
  api("/api/info").then((info) => {
    const el = $("#netInfo");
    if (!el) return;
    const urls = (info.lan || []).concat([info.local]).filter(Boolean);
    el.innerHTML = urls.map((u) => "<div><strong>" + esc(u) + "</strong></div>").join("") || "Lancez lancer-reseau.bat pour voir l'adresse du telephone.";
  }).catch(() => {});
}

async function saveSettings() {
  try {
    const body = {
      company_name: $("#sName").value,
      company_legal_form: $("#sForm").value,
      company_address: $("#sAddress").value,
      company_postal_code: $("#sCP").value,
      company_city: $("#sCity").value,
      company_country: $("#sCountry").value,
      company_email: $("#sEmail").value,
      company_phone: $("#sPhone").value,
      company_siret: $("#sSiret").value,
      company_tva: $("#sTva").value,
      company_iban: $("#sIban").value,
      company_bic: $("#sBic").value,
      payment_days: $("#sDays").value,
      invoice_prefix: $("#sPrefix").value,
      default_hourly_rate: $("#sRate").value,
      default_tva_rate: $("#sTvaRate").value,
      billing_tva: $("#sBillingTva").value,
      invoice_footer: $("#sFooter").value,
    };
    if ($("#sAccess") && $("#sAccess").value) body.access_code = $("#sAccess").value;
    state.settings = await api("/api/settings", { method: "PUT", body });
    toast("Parametres enregistres");
    showView("parametres");
  } catch (e) { toast(e.message); }
}
async function logoutServer() {
  try {
    await api("/api/logout", { method: "POST", body: {} });
    location.href = "/login";
  } catch (e) { location.href = "/login"; }
}

refreshAll().catch((e) => {
  $("#view-dashboard").innerHTML = `<div class="notice">${esc(e.message)}</div>`;
});
