const $ = (sel, root = document) => root.querySelector(sel);
const app = () => document.getElementById("app");

let me = null;
let notif = { count: 0, items: [] };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => {
    if (c === "&") return "&" + "amp;";
    if (c === "<") return "&" + "lt;";
    if (c === ">") return "&" + "gt;";
    if (c === '"') return "&" + "quot;";
    return "&#" + "39;";
  });
}
const money = (n) => `${Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} TND`;
const frDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
};
const initials = (name) => (name || "?").split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase();
const hue = (name) => [...(name || "x")].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
const avatar = (name) => `<span class="avatar" style="background:hsl(${hue(name)} 70% 42%)">${esc(initials(name))}</span>`;

function toast(message, kind = "ok") {
  const el = document.createElement("div");
  el.className = "toast-item" + (kind === "err" ? " err" : "");
  el.textContent = message;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  let body = opts.body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const res = await fetch("/api" + path, { method: opts.method || "GET", headers, body, credentials: "same-origin" });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data?.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

const STATUS = {
  PENDING: ["En attente", "MEDIUM"],
  DELIVERED: ["Livrée", "LOW"],
  REFUSED: ["Refusée", "HIGH"],
  NOT_COLLECTED: ["Non récupérée", "HIGH"],
};
const pill = (level, text) => `<span class="pill ${esc(level)}">${esc(text || level)}</span>`;
const statusPill = (s) => pill(STATUS[s]?.[1] || "UNKNOWN", STATUS[s]?.[0] || s);
const scoreChip = (score) => {
  if (score == null) return "—";
  const cls = score >= 75 ? "ok" : score >= 50 ? "mid" : "";
  return `<span class="score-chip ${cls}">${esc(score)}/100</span>`;
};
const engineLine = (engine) => engine
  ? `<div class="tag-engine"><i class="bi bi-cpu"></i> ${esc(engine.prediction_note || engine.calculated_by || "Calcul moteur")} · données fictives, calcul réel</div>`
  : "";

function parseHash() {
  const raw = (location.hash || "#/dashboard").replace(/^#/, "");
  const [path, qs] = raw.split("?");
  return { path: path || "/dashboard", params: new URLSearchParams(qs || "") };
}

async function boot() {
  try { me = await api("/me"); } catch { me = null; }
  if (me) notif = await api("/notifications").catch(() => notif);
  paint();
}

function paint() {
  if (!me) {
    app().innerHTML = loginView();
    bindLogin();
    return;
  }
  app().innerHTML = shellView();
  bindShell();
  route();
}

function loginView() {
  return `
  <div class="auth-wrap">
    <section class="auth-brand">
      <div>
        <div class="brand-mark"><div class="logo-badge"><i class="bi bi-shield-check"></i></div>
          <div><strong>TrustOrder AI</strong><span>COD · Tunisie</span></div></div>
        <h1>Prioriser les commandes à la livraison, sans accuser un client.</h1>
        <p class="lead">Le score est un indicateur de risque calculé par le moteur Python des Sprints 1 et 2. L'historique insuffisant reste en cold start : pas de probabilité inventée.</p>
        <div class="auth-points">
          <div><i class="bi bi-check2-circle"></i> Score 0–100, niveaux LOW / MEDIUM / HIGH</div>
          <div><i class="bi bi-check2-circle"></i> Priorité distincte du score de fiabilité</div>
          <div><i class="bi bi-check2-circle"></i> Import CSV, Excel et PDF texte, avec vérification humaine</div>
        </div>
      </div>
      <p class="fine">Données 100 % fictives · numéros +216 générés · aucune personne réelle.</p>
    </section>
    <section class="auth-panel">
      <form class="auth-card" id="login-form">
        <h2>Connexion</h2>
        <p class="fine">Session de démonstration. L'authentification Symfony Security est dans le backend source, elle n'est pas exécutée dans cet aperçu.</p>
        <div class="demo-accounts">
          <button type="button" data-fill="emna.bensalah@maison-emna.tn|Boutique2026!">
            Emna Ben Salah <small>Boutique Maison Emna · Boutique2026!</small>
          </button>
          <button type="button" data-fill="admin@trustorder.tn|Admin2026!">
            Sami Khelifi <small>Administrateur · Admin2026!</small>
          </button>
        </div>
        <label class="form-label">E-mail</label>
        <input class="form-control mb-2" name="email" type="email" required autocomplete="username">
        <label class="form-label">Mot de passe</label>
        <input class="form-control mb-3" name="password" type="password" required autocomplete="current-password">
        <button class="btn btn-accent w-100" type="submit">Entrer</button>
      </form>
    </section>
  </div>`;
}

function bindLogin() {
  document.querySelectorAll("[data-fill]").forEach((btn) => btn.addEventListener("click", () => {
    const [email, password] = btn.dataset.fill.split("|");
    $("[name=email]").value = email;
    $("[name=password]").value = password;
  }));
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      me = await api("/login", { method: "POST", body: { email: fd.get("email"), password: fd.get("password") } });
      notif = await api("/notifications");
      location.hash = "#/dashboard";
      paint();
    } catch (err) { toast(err.message, "err"); }
  });
}

function navItem(path, icon, label, badge) {
  const active = parseHash().path === path ? "active" : "";
  const b = badge ? `<span class="badge-count">${badge}</span>` : "";
  return `<a class="side-link ${active}" href="#${path}"><i class="bi ${icon}"></i>${esc(label)}${b}</a>`;
}

function shellView() {
  const shop = me.role === "SHOP";
  const adminBlock = me.role === "ADMIN" ? `
    <div class="nav-label">ADMINISTRATION</div>
    ${navItem("/admin", "bi-gear", "Administration")}
    ${navItem("/admin/stats", "bi-bar-chart", "Statistiques globales")}` : "";
  return `
  <div class="shell" id="shell">
    <aside class="sidebar" id="sidebar">
      <div class="brand-mark px-2 mb-2"><div class="logo-badge"><i class="bi bi-shield-check"></i></div>
        <div><strong>TrustOrder AI</strong><span>${shop ? "Console boutique" : "Console admin"}</span></div></div>
      <div class="nav-label">PILOTAGE</div>
      ${navItem("/dashboard", "bi-grid", "Tableau de bord")}
      ${navItem("/orders", "bi-box", "Commandes")}
      ${navItem("/verify", "bi-search", "Vérification")}
      <div class="nav-label">INTELLIGENCE</div>
      ${navItem("/priority", "bi-lightning", "Priorisation IA")}
      ${navItem("/scoring", "bi-shield", "Scoring & Risque")}
      ${shop ? navItem("/import", "bi-file-earmark-arrow-up", "Import Excel / OCR") : ""}
      <div class="nav-label">GESTION</div>
      ${navItem("/complaints", "bi-exclamation-triangle", "Signalements", notif.count || "")}
      ${navItem("/contestations", "bi-chat-left-text", "Contestations")}
      ${navItem("/history", "bi-clock-history", "Historique IA")}
      ${adminBlock}
      <div class="side-user">
        ${avatar(me.full_name)}
        <div class="who"><strong>${esc(me.full_name)}</strong><span>${esc(me.boutique?.name || me.email)}</span></div>
        <button class="btn btn-ghost btn-sm" id="logout" title="Déconnexion"><i class="bi bi-box-arrow-right"></i></button>
      </div>
    </aside>
    <section class="main">
      <header class="topbar">
        <button class="icon-btn menu-btn" id="open-side" aria-label="Menu"><i class="bi bi-list"></i></button>
        <div class="greet" id="greet"></div>
        <form class="search-mini" id="quick-search">
          <i class="bi bi-search"></i>
          <input name="q" placeholder="Rechercher un téléphone, une commande…" aria-label="Recherche">
        </form>
        <div style="position:relative">
          <button class="icon-btn" id="bell" aria-label="Notifications"><i class="bi bi-bell"></i>
            ${notif.count ? `<span class="dot">${notif.count}</span>` : ""}</button>
          <div class="card-dark bell-pop d-none" id="bell-pop"></div>
        </div>
        ${shop ? `<button class="btn btn-accent" data-bs-toggle="modal" data-bs-target="#orderModal"><i class="bi bi-plus-lg"></i> Nouvelle commande</button>` : ""}
      </header>
      <div id="view"></div>
    </section>
  </div>
  <div class="modal fade" id="orderModal" tabindex="-1"><div class="modal-dialog"><form class="modal-content" id="order-form">
    <div class="modal-header"><h5 class="modal-title">Nouvelle commande</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <label class="form-label">Téléphone</label><input class="form-control mb-2" name="phone" placeholder="98 111 222 ou +216…" required>
      <label class="form-label">Libellé</label><input class="form-control mb-2" name="label" required>
      <label class="form-label">Montant (TND)</label><input class="form-control" name="amount" type="number" min="0.1" step="0.001" required>
      <p class="fine mt-2">La priorité affichée ensuite est calculée par moteur.prioriser_commande, pas saisie à la main.</p>
    </div>
    <div class="modal-footer"><button class="btn btn-accent" type="submit">Enregistrer et analyser</button></div>
  </form></div></div>
  <div class="modal fade" id="resultModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title">Résultat du moteur</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body" id="result-body"></div>
  </div></div></div>`;
}

function bindShell() {
  $("#logout").addEventListener("click", async () => {
    await api("/logout", { method: "POST" });
    me = null;
    location.hash = "#/dashboard";
    paint();
  });
  $("#open-side")?.addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $("#quick-search").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = new FormData(e.target).get("q");
    location.hash = "#/verify?q=" + encodeURIComponent(q || "");
  });
  $("#bell").addEventListener("click", () => {
    const pop = $("#bell-pop");
    pop.classList.toggle("d-none");
    pop.innerHTML = `<strong>Signalements en attente</strong>` + (notif.items.length
      ? notif.items.map((i) => `<div class="mt-2"><div>${esc(i.motif)}</div><div class="fine">${esc(i.phone_mask)} · ${esc(i.created_at)}</div></div>`).join("")
      : `<p class="fine mb-0 mt-2">Rien en attente.</p>`) + `<a class="d-inline-block mt-2" href="#/complaints">Voir tout</a>`;
  });
  $("#order-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const res = await api("/orders", { method: "POST", body: { phone: fd.get("phone"), label: fd.get("label"), amount: Number(fd.get("amount")) } });
      bootstrap.Modal.getOrCreateInstance($("#orderModal")).hide();
      e.target.reset();
      showResult(res);
      toast("Commande créée. Priorité calculée par le moteur.");
      notif = await api("/notifications");
      route();
    } catch (err) { toast(err.message, "err"); }
  });
}

function showResult(res) {
  const a = res.analysis || {};
  const p = res.priority || {};
  $("#result-body").innerHTML = `
    ${engineLine(res.engine)}
    <div class="row g-3 mt-1">
      <div class="col-md-6"><div class="card-dark">
        <div class="fine">Score de fiabilité</div>
        <div class="kpi-value">${a.score ?? "—"}<small>/100</small></div>
        ${pill(a.risk_level, a.risk_level)} <span class="fine">${esc(a.recommendation || "")}</span>
        ${(a.factors || []).map((f) => `<div class="factor"><span>${esc(f.label)}</span><b>${f.points > 0 ? "+" : ""}${esc(f.points)}</b></div>`).join("")}
      </div></div>
      <div class="col-md-6"><div class="card-dark">
        <div class="fine">Priorité de la commande (indicateur différent)</div>
        <div class="kpi-value">${p.priority_score ?? "—"}<small>/100</small></div>
        ${pill(p.priority, p.priority)}
        <p class="mt-2">${esc(p.explanation || "")}</p>
        <p class="fine">${a.cold_start ? "Cold start : probabilité ML non calculée." : `Rétention ML : ${Math.round((a.retention_probability || 0) * 1000) / 10} % (${esc(a.model_version)})`}</p>
      </div></div>
    </div>`;
  bootstrap.Modal.getOrCreateInstance($("#resultModal")).show();
}

function setGreet(title, sub) {
  const el = $("#greet");
  if (el) el.innerHTML = `<h1>${esc(title)}</h1><p>${sub}</p>`;
}

async function route() {
  const { path, params } = parseHash();
  document.querySelectorAll(".side-link").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + path));
  const view = $("#view");
  if (!view) return;
  $("#sidebar")?.classList.remove("open");
  view.innerHTML = `<div class="fine">Chargement…</div>`;
  try {
    if (path === "/dashboard") await renderDashboard(view);
    else if (path === "/orders") await renderOrders(view, params);
    else if (path === "/verify") await renderVerify(view, params);
    else if (path === "/priority") await renderPriority(view);
    else if (path === "/scoring") await renderScoring(view);
    else if (path === "/import") await renderImport(view);
    else if (path === "/complaints") await renderComplaints(view);
    else if (path === "/contestations") await renderContestations(view);
    else if (path === "/history") await renderHistory(view, params);
    else if (path === "/admin" || path.startsWith("/admin")) await renderAdmin(view, path);
    else view.innerHTML = `<div class="card-dark">Page introuvable.</div>`;
  } catch (err) {
    view.innerHTML = `<div class="card-dark issue-error">${esc(err.message)}</div>`;
  }
}

function kpi(label, value, sub, icon) {
  return `<article class="card-dark"><div class="kpi-top">${esc(label)}<span class="kpi-ico"><i class="bi ${icon}"></i></span></div>
    <div class="kpi-value">${value}</div><div class="delta ${sub.cls || "flat"}">${sub.html}</div></article>`;
}

async function renderDashboard(view) {
  const d = await api("/dashboard");
  const title = me.role === "SHOP" ? "Tableau de bord" : "Tableau de bord global";
  setGreet(title, `Bonjour <b>${esc(me.full_name)}</b>, activité du ${frDate(d.date)}.`);
  const deltaOrders = d.orders_delta_pct == null ? "pas de comparaison (hier = 0)" : `${d.orders_delta_pct > 0 ? "+" : ""}${d.orders_delta_pct} % vs hier`;
  const deltaScore = d.mean_score_delta_7d == null ? "calcul live" : `${d.mean_score_delta_7d > 0 ? "+" : ""}${d.mean_score_delta_7d} pt vs J-7 (règles)`;
  const totalRisk = (d.risk.LOW + d.risk.MEDIUM + d.risk.HIGH) || 1;
  const pct = (n) => Math.round(100 * n / totalRisk);
  view.innerHTML = `
    <div class="grid-kpi">
      ${kpi("Commandes du jour", esc(d.orders_today), { html: esc(deltaOrders), cls: (d.orders_delta_pct || 0) >= 0 ? "" : "down" }, "bi-bag")}
      ${kpi("Score de fiabilité moyen", `${d.mean_score ?? "—"}<small>/100</small>`, { html: esc(deltaScore) }, "bi-shield")}
      ${kpi("Commandes HIGH priority", esc(d.high_priority_pending), { html: "en attente · action utile", cls: "down" }, "bi-exclamation-triangle")}
      ${kpi("Rétention ML moyenne", d.mean_retention == null ? "—" : `${d.mean_retention}<small>%</small>`, { html: d.mean_retention == null ? "aucun client hors cold start" : `${esc(d.model_version)} · ${d.retention_sample} clients`, cls: "" }, "bi-activity")}
    </div>
    <div class="layout-2">
      <section class="card-dark">
        <div class="section-h"><h2><i class="bi bi-lightning-charge"></i> AI Order Prioritization <span class="live">LIVE</span></h2><a href="#/priority">Tout voir</a></div>
        <div class="table-wrap"><table class="data"><thead><tr><th>Client</th><th>Score</th><th>Priorité</th><th>Raison du moteur</th></tr></thead><tbody>
          ${d.priority_preview.map((r) => `<tr>
            <td><div class="person">${avatar(r.customer)}<div>${esc(r.customer)}<div class="sub">${esc(r.phone_mask)}</div></div></div></td>
            <td>${scoreChip(r.score)}</td><td>${pill(r.priority, r.priority)}</td>
            <td>${esc(r.explanation)}</td></tr>`).join("") || `<tr><td colspan="4" class="fine">Aucune commande en attente.</td></tr>`}
        </tbody></table></div>
      </section>
      <section class="card-dark">
        <div class="section-h"><h2><i class="bi bi-pie-chart"></i> Niveaux de risque</h2></div>
        <div class="gauge"><div class="num">${d.mean_score ?? "—"}</div><div class="fine">score global moyen · calculé maintenant</div></div>
        <div class="bars">
          ${["LOW", "MEDIUM", "HIGH"].map((k, i) => {
            const label = ["Faible", "Moyen", "Élevé"][i];
            const color = ["#3dd68c", "#f5b942", "#ff5d7a"][i];
            return `<div class="bar-row"><span>${label}</span><div class="bar"><span style="width:${pct(d.risk[k])}%;background:${color}"></span></div><b>${pct(d.risk[k])}%</b></div>`;
          }).join("")}
        </div>
        <div class="note">Cold start actif sur ${esc(d.cold_start_pct)} % des numéros (${esc(d.cold_start_count)}). Le moteur de règles est utilisé : la probabilité ML n'est pas affichée pour ces clients.</div>
      </section>
    </div>
    <section class="card-dark mt-3">
      <div class="section-h"><h2>Dernières commandes</h2><a href="#/orders">Voir tout</a></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>ID</th><th>Client</th><th>Libellé</th><th>Statut</th><th>Montant</th><th>Date</th></tr></thead><tbody>
        ${d.recent_orders.map((o) => `<tr><td>#${o.id}</td><td>${esc(o.full_name)}<div class="fine">${esc(o.phone_mask)}</div></td><td>${esc(o.label)}</td><td>${statusPill(o.status)}</td><td>${money(o.amount)}</td><td>${esc(o.order_date)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="fine mt-2">${esc(d.engine.calculated_by)}. Les pourcentages de risque sont recomptés sur les clients de ce périmètre, pas figés dans la base.</p>
    </section>`;
}

async function renderOrders(view, params) {
  setGreet("Commandes", "Historique de votre boutique. Les autres boutiques ne voient pas ces lignes.");
  const page = Number(params.get("page") || 1);
  const status = params.get("status") || "";
  const q = params.get("q") || "";
  const data = await api(`/orders?page=${page}&status=${encodeURIComponent(status)}&q=${encodeURIComponent(q)}`);
  view.innerHTML = `
    <form class="filters" id="order-filters">
      <input class="form-control" style="max-width:260px" name="q" value="${esc(q)}" placeholder="Client, produit, téléphone">
      <select class="form-select" style="max-width:200px" name="status">
        ${["", "PENDING", "DELIVERED", "REFUSED", "NOT_COLLECTED"].map((s) => `<option value="${s}" ${s === status ? "selected" : ""}>${s ? STATUS[s][0] : "Tous les statuts"}</option>`).join("")}
      </select>
      <button class="btn btn-ghost" type="submit">Filtrer</button>
    </form>
    <section class="card-dark table-wrap"><table class="data"><thead><tr><th>ID</th><th>Client</th><th>Libellé</th><th>Statut</th><th>Montant</th><th>Date</th><th></th></tr></thead><tbody>
      ${data.items.map((o) => `<tr>
        <td>#${o.id}</td>
        <td>${esc(o.full_name)}<div class="fine">${esc(o.phone_mask)}${o.phone_normalized ? ` · <button class="btn btn-link btn-sm p-0" data-reveal="${esc(o.phone_normalized)}">afficher</button>` : ""}</div></td>
        <td>${esc(o.label)}${me.role === "ADMIN" ? `<div class="fine">${esc(o.shop)}</div>` : ""}</td>
        <td>${statusPill(o.status)}</td><td>${money(o.amount)}</td><td>${esc(o.order_date)}</td>
        <td>${o.status === "PENDING" && (me.role === "SHOP" || me.role === "ADMIN") ? `<button class="btn btn-ghost btn-sm" data-confirm="${o.id}">Confirmer l'issue</button>` : ""}</td>
      </tr>`).join("") || `<tr><td colspan="7">Aucune commande.</td></tr>`}
    </tbody></table>
    <div class="pager"><span>${data.total} commandes</span>
      <button class="btn btn-ghost btn-sm" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>Précédent</button>
      <span>${page}</span>
      <button class="btn btn-ghost btn-sm" data-page="${page + 1}" ${page * data.page_size >= data.total ? "disabled" : ""}>Suivant</button>
    </div></section>`;
  $("#order-filters").addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    location.hash = `#/orders?q=${encodeURIComponent(fd.get("q"))}&status=${encodeURIComponent(fd.get("status"))}`;
  });
  view.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => {
    params.set("page", b.dataset.page);
    location.hash = "#/orders?" + params.toString();
  }));
  view.querySelectorAll("[data-reveal]").forEach((b) => b.addEventListener("click", () => { b.textContent = "+" + b.dataset.reveal; }));
  view.querySelectorAll("[data-confirm]").forEach((b) => b.addEventListener("click", async () => {
    const status = prompt("Issue : DELIVERED, REFUSED ou NOT_COLLECTED", "DELIVERED");
    if (!status) return;
    try {
      await api(`/orders/${b.dataset.confirm}/confirm`, { method: "POST", body: { status: status.trim() } });
      toast("Issue enregistrée.");
      route();
    } catch (err) { toast(err.message, "err"); }
  }));
}

async function renderVerify(view, params) {
  setGreet("Vérification", "Recherche unitaire et contrôle d'une liste. Le numéro complet n'est pas renvoyé à un service tiers : seul l'historique agrégé entre dans le moteur.");
  const preset = params.get("q") || "";
  view.innerHTML = `
    <ul class="nav nav-pills mb-3">
      <li class="nav-item"><button class="nav-link active" data-tab="one">Un numéro</button></li>
      <li class="nav-item"><button class="nav-link" data-tab="many">Vérification en masse</button></li>
    </ul>
    <section id="tab-one" class="card-dark">
      <form id="search-form" class="d-flex gap-2 flex-wrap">
        <input class="form-control" style="max-width:320px" name="telephone" value="${esc(preset)}" placeholder="+216 ou 8 chiffres" required>
        <button class="btn btn-accent" type="submit">Analyser</button>
      </form>
      <div id="search-out" class="mt-3"></div>
    </section>
    <section id="tab-many" class="card-dark d-none mt-3">
      <form id="bulk-form">
        <textarea class="form-control" name="phones" rows="6" placeholder="Un numéro par ligne"></textarea>
        <div class="d-flex gap-2 mt-2 flex-wrap">
          <button class="btn btn-accent" type="submit">Analyser la liste</button>
          <label class="btn btn-ghost mb-0">Importer un CSV<input type="file" id="bulk-file" accept=".csv,.xlsx,.txt" hidden></label>
          <a href="/samples/numeros_a_verifier.csv">Exemple CSV</a>
        </div>
      </form>
      <div id="bulk-out" class="mt-3"></div>
    </section>`;
  view.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    view.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("active", x === b));
    $("#tab-one").classList.toggle("d-none", b.dataset.tab !== "one");
    $("#tab-many").classList.toggle("d-none", b.dataset.tab !== "many");
  }));
  $("#search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const tel = new FormData(e.target).get("telephone");
      const res = await api("/clients?telephone=" + encodeURIComponent(tel));
      $("#search-out").innerHTML = clientCard(res);
      bindClientActions($("#search-out"), tel);
    } catch (err) { toast(err.message, "err"); }
  });
  if (preset) $("#search-form").requestSubmit();
  $("#bulk-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const phones = new FormData(e.target).get("phones").split(/\n|,/).map((s) => s.trim()).filter(Boolean);
    try { $("#bulk-out").innerHTML = bulkTable(await api("/bulk", { method: "POST", body: { phones } })); }
    catch (err) { toast(err.message, "err"); }
  });
  $("#bulk-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("fichier", file);
    try { $("#bulk-out").innerHTML = bulkTable(await api("/bulk/file", { method: "POST", body: fd })); }
    catch (err) { toast(err.message, "err"); }
  });
}

function clientCard(res) {
  const a = res.analysis;
  const ml = a.cold_start || a.retention_probability == null
    ? "Probabilité ML non calculée (cold start ou client inconnu)."
    : `Rétention ${Math.round(a.retention_probability * 1000) / 10} % · ${a.model_version} · source ${a.prediction_source}`;
  return `${engineLine(res.engine)}
    <div class="row g-3 mt-1">
      <div class="col-lg-5"><div class="card-dark">
        <div class="person">${avatar(res.customer?.full_name || "Inconnu")}<div><strong>${esc(res.customer?.full_name || "Client inconnu de la base")}</strong><div class="sub">${esc(res.phone_mask)}${res.customer ? " · " + esc(res.customer.city) + ", " + esc(res.customer.governorate) : ""}</div></div></div>
        <div class="kpi-value">${a.score}<small>/100</small></div>
        ${pill(a.risk_level, a.risk_level)}
        <p>${esc(a.recommendation)}</p>
        <p class="fine">${esc(ml)}</p>
        <p class="fine">${esc(res.cross_shop_note)}</p>
      </div></div>
      <div class="col-lg-7"><div class="card-dark">
        <h3 class="h6">Pourquoi ce score</h3>
        ${(a.factors || []).map((f) => `<div class="factor"><span>${esc(f.label)}</span><b>${f.points > 0 ? "+" : ""}${esc(f.points)}</b></div>`).join("")}
        <h3 class="h6 mt-3">Historique chiffré transmis au moteur</h3>
        <p class="fine mb-2">Livrées ${res.history.delivered_orders} · Refusées ${res.history.refused_orders} · Non récupérées ${res.history.not_collected_orders} · Échecs 90 j ${res.history.recent_failed_90d} · Boutiques ${res.history.distinct_shops} · Signalements confirmés ${res.history.reports_count}</p>
        <h3 class="h6">Commandes visibles pour votre périmètre</h3>
        <div class="table-wrap"><table class="data"><tbody>
          ${(res.shop_orders || []).map((o) => `<tr><td>${esc(o.order_date)}</td><td>${esc(o.label)}</td><td>${money(o.amount)}</td><td>${statusPill(o.status)}</td><td class="fine">${esc(o.shop || "")}</td></tr>`).join("") || `<tr><td class="fine">Aucune commande dans ce périmètre.</td></tr>`}
        </tbody></table></div>
        ${me.role === "SHOP" ? `<div class="d-flex gap-2 mt-3">
          <button class="btn btn-ghost btn-sm" id="btn-report">Signaler</button>
          <button class="btn btn-ghost btn-sm" id="btn-contest">Contester</button>
        </div>` : ""}
      </div></div>
    </div>`;
}

function bindClientActions(root, phone) {
  root.querySelector("#btn-report")?.addEventListener("click", () => openCase("/complaints", phone));
  root.querySelector("#btn-contest")?.addEventListener("click", () => openCase("/contestations", phone));
}
function openCase(path, phone) {
  const motif = prompt(path.includes("contest") ? "Motif de la contestation" : "Motif du signalement");
  if (!motif) return;
  const url = path.includes("contest") ? "/contestations" : "/complaints";
  api(url, { method: "POST", body: { phone, motif } }).then(() => toast("Enregistré.")).catch((e) => toast(e.message, "err"));
}

function bulkTable(data) {
  const s = data.summary;
  return `${engineLine({ prediction_note: "Chaque ligne ANALYZED appelle moteur.analyser_client. UNKNOWN et INVALID n'ont pas de score inventé." })}
    <div class="d-flex gap-2 flex-wrap my-2">${pill("LOW", "LOW " + s.LOW)} ${pill("MEDIUM", "MEDIUM " + s.MEDIUM)} ${pill("HIGH", "HIGH " + s.HIGH)} <span class="fine">${s.unknown_customers} inconnus · ${s.invalid_numbers} invalides · ${s.total} lignes</span></div>
    <div class="table-wrap"><table class="data"><thead><tr><th>Saisi</th><th>Masqué</th><th>Type</th><th>Commandes</th><th>Score</th><th>Risque</th><th>ML</th><th>Recommandation</th></tr></thead><tbody>
      ${data.results.map((r) => `<tr><td>${esc(r.input)}</td><td>${esc(r.phone_mask || "—")}</td><td>${esc(r.result_type)}</td><td>${esc(r.orders)}</td><td>${r.score ?? "—"}</td><td>${r.risk_level ? pill(r.risk_level, r.risk_level) : "—"}</td><td>${r.cold_start ? "non calculée" : (r.retention_probability == null ? "—" : Math.round(r.retention_probability * 100) + " %")}</td><td>${esc(r.recommendation)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

async function renderPriority(view) {
  setGreet("Priorisation IA", "PriorityScore = 60 % risque + 25 % montant + 15 % incertitude. Ce n'est pas le score de fiabilité.");
  const data = await api("/priority");
  view.innerHTML = `<section class="card-dark table-wrap"><table class="data"><thead><tr><th>Client</th><th>Commande</th><th>Montant</th><th>Fiabilité</th><th>Priorité</th><th>Explication du moteur</th></tr></thead><tbody>
    ${data.items.map((r) => `<tr>
      <td><div class="person">${avatar(r.customer)}<div>${esc(r.customer)}<div class="sub">${esc(r.phone_mask)}${r.cold_start ? " · cold start" : ""}</div></div></div></td>
      <td>${esc(r.label)}<div class="fine">${esc(r.order_date)} · ${esc(r.shop)}</div></td>
      <td>${money(r.amount)}</td><td>${scoreChip(r.score)}</td><td>${pill(r.priority, r.priority)} <span class="fine">${r.priority_score}</span></td>
      <td>${esc(r.explanation)}</td></tr>`).join("")}
  </tbody></table><p class="fine mt-2">${esc(data.engine.calculated_by)} · tri live.</p></section>`;
}

async function renderScoring(view) {
  setGreet("Scoring & Risque", "Les seuils et la formule sont ceux de config.py / scoring.py. Le contrôle ci-dessous interroge le moteur, il ne recopie pas un tableau.");
  const info = await api("/engine");
  view.innerHTML = `
    <div class="card-dark mb-3">
      <strong>Auto-contrôle du moteur</strong>
      <p class="mb-1">Client sans historique : score ${info.self_check_unknown_customer_score}/100 (attendu ${info.self_check_expected}) — ${info.self_check_ok ? "conforme" : "écart"}.</p>
      <p class="fine mb-0">Cold start sous ${info.min_history} issues · LOW ≥ ${info.risk_thresholds.LOW} · MEDIUM ≥ ${info.risk_thresholds.MEDIUM} · priorité HIGH ≥ ${info.priority_thresholds.HIGH} · MEDIUM ≥ ${info.priority_thresholds.MEDIUM} · poids ${info.weights.risk}/${info.weights.amount}/${info.weights.uncertainty} · plafond ${info.amount_cap_tnd} TND · fichiers ${info.source_files.join(", ")} · formules modifiées : ${info.formulas_modified ? "oui" : "non"}.</p>
    </div>
    <form class="card-dark" id="sim-form">
      <h2 class="h5">Simuler un historique</h2>
      <p class="fine">Vous saisissez des compteurs. Le serveur appelle moteur.analyser_client. Ce n'est pas une commande réelle.</p>
      <div class="row g-2">
        ${[["delivered_orders", "Livrées"], ["refused_orders", "Refusées"], ["not_collected_orders", "Non récupérées"], ["recent_failed_90d", "Échecs 90 j"], ["distinct_shops", "Boutiques"], ["reports_count", "Signalements"]].map(([k, lab]) => `<div class="col-6 col-md-4"><label class="form-label">${lab}</label><input class="form-control" name="${k}" type="number" min="0" value="0"></div>`).join("")}
        <div class="col-6 col-md-4"><label class="form-label">Montant TND (priorité)</label><input class="form-control" name="amount" type="number" min="1" step="0.001" value="120"></div>
      </div>
      <button class="btn btn-accent mt-3" type="submit">Calculer avec le moteur</button>
      <div id="sim-out" class="mt-3"></div>
    </form>`;
  $("#sim-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const history = {};
    for (const [k] of [["delivered_orders"], ["refused_orders"], ["not_collected_orders"], ["recent_failed_90d"], ["distinct_shops"], ["reports_count"]]) history[k] = Number(fd.get(k));
    try {
      const res = await api("/simulate", { method: "POST", body: { history, amount: Number(fd.get("amount")) } });
      $("#sim-out").innerHTML = `<div class="note">${esc(res.warning)}</div>` + clientCard({ ...res, customer: null, shop_orders: [], phone_mask: "simulation", cross_shop_note: res.priority.explanation });
    } catch (err) { toast(err.message, "err"); }
  });
}

let currentLot = null;
async function renderImport(view) {
  if (me.role !== "SHOP") { view.innerHTML = `<div class="card-dark">Import réservé à une boutique.</div>`; return; }
  setGreet("Import Excel / OCR", "Rien n'est enregistré tant que vous n'avez pas validé le lot. Les lignes en erreur restent dehors.");
  view.innerHTML = `
    <div class="row g-3">
      <div class="col-md-6"><form class="card-dark drop" id="form-csv">
        <i class="bi bi-filetype-csv" style="font-size:28px"></i>
        <h2 class="h5 mt-2">Excel ou CSV</h2>
        <p class="fine">Colonnes détectées automatiquement (téléphone, statut, montant, date, libellé).</p>
        <input class="form-control" type="file" name="fichier" accept=".csv,.xlsx,.xlsm,.txt" required>
        <button class="btn btn-accent mt-2" type="submit">Lire le fichier</button>
        <div class="mt-2"><a href="/samples/commandes_exemple.csv">CSV d'exemple</a></div>
      </form></div>
      <div class="col-md-6"><form class="card-dark drop" id="form-doc">
        <i class="bi bi-file-earmark-pdf" style="font-size:28px"></i>
        <h2 class="h5 mt-2">PDF ou image</h2>
        <p class="fine">PDF texte : extraction directe. Image / PDF scanné : Tesseract, message clair s'il n'est pas installé.</p>
        <input class="form-control" type="file" name="fichier" accept=".pdf,image/*" required>
        <button class="btn btn-accent mt-2" type="submit">Extraire</button>
        <div class="mt-2"><a href="/samples/bordereau_exemple.pdf">Bordereau PDF exemple</a></div>
      </form></div>
    </div>
    <div id="lot" class="mt-3"></div>`;
  $("#form-csv").addEventListener("submit", (e) => sendImport(e, "/import/file"));
  $("#form-doc").addEventListener("submit", (e) => sendImport(e, "/import/document"));
}

async function sendImport(e, path) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    currentLot = await api(path, { method: "POST", body: fd });
    paintLot();
  } catch (err) { toast(err.message, "err"); }
}

function paintLot() {
  const lot = currentLot;
  const box = $("#lot");
  if (!box || !lot) return;
  const s = lot.summary;
  box.innerHTML = `<section class="card-dark">
    <div class="section-h"><h2>Lot ${esc(lot.lot_id)} · ${esc(lot.filename)}</h2><span class="fine">${esc(lot.status)} · ${s.valid} valides · ${s.with_errors} erreurs · ${s.with_warnings} avertissements</span></div>
    <p class="fine">Colonnes : ${esc(JSON.stringify(lot.info.detected_columns || lot.info))}</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>#</th><th>Téléphone</th><th>Statut</th><th>Montant</th><th>Date</th><th>Libellé</th><th>Ignorer</th><th></th></tr></thead><tbody>
      ${lot.lines.map((l) => `<tr data-line="${l.line}">
        <td>${l.line}<div>${(l.issues || []).map((i) => `<div class="issue-${i.level}">${esc(i.message)}</div>`).join("")}</div></td>
        <td><input class="form-control form-control-sm" name="phone" value="${esc(l.phone)}"></td>
        <td><input class="form-control form-control-sm" name="status" value="${esc(l.status)}"></td>
        <td><input class="form-control form-control-sm" name="amount" value="${esc(l.amount)}"></td>
        <td><input class="form-control form-control-sm" name="order_date" value="${esc(l.order_date)}"></td>
        <td><input class="form-control form-control-sm" name="label" value="${esc(l.label)}"></td>
        <td><input type="checkbox" name="ignore" ${l.ignore ? "checked" : ""}></td>
        <td><button class="btn btn-ghost btn-sm" data-save="${l.line}" ${lot.status !== "A_VERIFIER" ? "disabled" : ""}>Corriger</button></td>
      </tr>`).join("")}
    </tbody></table></div>
    ${lot.report ? `<pre class="fine mt-2">${esc(JSON.stringify(lot.report, null, 2))}</pre>` : `<button class="btn btn-accent mt-3" id="validate-lot" ${lot.status !== "A_VERIFIER" ? "disabled" : ""}>Valider et enregistrer les lignes correctes</button>`}
  </section>`;
  box.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", async () => {
    const row = box.querySelector(`[data-line="${b.dataset.save}"]`);
    const body = {};
    row.querySelectorAll("input").forEach((input) => { body[input.name] = input.type === "checkbox" ? input.checked : input.value; });
    try {
      currentLot = await api(`/lots/${lot.lot_id}/lines/${b.dataset.save}`, { method: "PATCH", body });
      paintLot();
      toast("Ligne recontrôlée.");
    } catch (err) { toast(err.message, "err"); }
  }));
  $("#validate-lot")?.addEventListener("click", async () => {
    try {
      const report = await api(`/lots/${lot.lot_id}/validate`, { method: "POST" });
      currentLot = await api(`/lots/${lot.lot_id}`);
      paintLot();
      toast(`${report.report.inserted} commande(s) enregistrée(s).`);
    } catch (err) { toast(err.message, "err"); }
  });
}

async function renderComplaints(view) {
  setGreet("Signalements", me.role === "ADMIN" ? "Confirmer un signalement l'ajoute au score (reports_count)." : "Un signalement en attente ne change pas le score tant qu'un admin ne l'a pas confirmé.");
  const data = await api("/complaints");
  view.innerHTML = `${me.role === "SHOP" ? `<form class="card-dark mb-3" id="c-form"><div class="row g-2">
      <div class="col-md-4"><input class="form-control" name="phone" placeholder="Téléphone" required></div>
      <div class="col-md-6"><input class="form-control" name="motif" placeholder="Motif" required></div>
      <div class="col-md-2"><button class="btn btn-accent w-100" type="submit">Signaler</button></div>
    </div></form>` : ""}
    <section class="card-dark table-wrap"><table class="data"><thead><tr><th>#</th><th>Boutique</th><th>Numéro</th><th>Motif</th><th>Statut</th><th>Note</th>${me.role === "ADMIN" ? "<th></th>" : ""}</tr></thead><tbody>
      ${data.items.map((c) => `<tr><td>${c.id}</td><td>${esc(c.shop)}</td><td>${esc(c.phone_mask)}</td><td>${esc(c.motif)}</td><td>${esc(c.status)}</td><td class="fine">${esc(c.admin_note || "")}</td>
        ${me.role === "ADMIN" ? `<td><button class="btn btn-ghost btn-sm" data-decide="CONFIRME" data-id="${c.id}">Confirmer</button> <button class="btn btn-ghost btn-sm" data-decide="REJETE" data-id="${c.id}">Rejeter</button></td>` : ""}</tr>`).join("")}
    </tbody></table></section>`;
  $("#c-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try { await api("/complaints", { method: "POST", body: { phone: fd.get("phone"), motif: fd.get("motif") } }); toast("Signalement créé."); route(); }
    catch (err) { toast(err.message, "err"); }
  });
  view.querySelectorAll("[data-decide]").forEach((b) => b.addEventListener("click", async () => {
    const note = prompt("Note de décision", "") || "";
    try { await api(`/admin/complaints/${b.dataset.id}`, { method: "PATCH", body: { status: b.dataset.decide, note } }); route(); }
    catch (err) { toast(err.message, "err"); }
  }));
}

async function renderContestations(view) {
  setGreet("Contestations", "Une contestation ne modifie pas automatiquement le score. L'admin tranche et l'historique de la décision est conservé.");
  const data = await api("/contestations");
  view.innerHTML = `${me.role === "SHOP" ? `<form class="card-dark mb-3" id="k-form"><div class="row g-2">
      <div class="col-md-4"><input class="form-control" name="phone" placeholder="Téléphone concerné" required></div>
      <div class="col-md-6"><input class="form-control" name="motif" placeholder="Ce qui est contesté" required></div>
      <div class="col-md-2"><button class="btn btn-accent w-100">Ouvrir</button></div>
    </div></form>` : ""}
    <section class="card-dark table-wrap"><table class="data"><thead><tr><th>#</th><th>Boutique</th><th>Numéro</th><th>Motif</th><th>Statut</th><th>Décision</th>${me.role === "ADMIN" ? "<th></th>" : ""}</tr></thead><tbody>
      ${data.items.map((c) => `<tr><td>${c.id}</td><td>${esc(c.shop)}</td><td>${esc(c.phone_mask)}</td><td>${esc(c.motif)}</td><td>${esc(c.status)}</td><td class="fine">${esc(c.decision_note || "")}</td>
        ${me.role === "ADMIN" ? `<td>
          <button class="btn btn-ghost btn-sm" data-st="EN_COURS" data-id="${c.id}">En cours</button>
          <button class="btn btn-ghost btn-sm" data-st="ACCEPTEE" data-id="${c.id}">Accepter</button>
          <button class="btn btn-ghost btn-sm" data-st="REJETEE" data-id="${c.id}">Rejeter</button></td>` : ""}</tr>`).join("")}
    </tbody></table></section>`;
  $("#k-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try { await api("/contestations", { method: "POST", body: { phone: fd.get("phone"), motif: fd.get("motif") } }); toast("Contestation ouverte."); route(); }
    catch (err) { toast(err.message, "err"); }
  });
  view.querySelectorAll("[data-st]").forEach((b) => b.addEventListener("click", async () => {
    const note = prompt("Note de décision") || "";
    try { await api(`/admin/contestations/${b.dataset.id}`, { method: "PATCH", body: { status: b.dataset.st, note } }); route(); }
    catch (err) { toast(err.message, "err"); }
  }));
}

async function renderHistory(view, params) {
  setGreet("Historique des analyses", "Journal des calculs réellement demandés pendant cette démo (recherches, créations). Les scores du tableau de bord, eux, sont recalculés à l'affichage.");
  const page = Number(params.get("page") || 1);
  const data = await api("/analyses?page=" + page);
  view.innerHTML = `<section class="card-dark table-wrap"><table class="data"><thead><tr><th>Quand</th><th>Qui</th><th>Numéro</th><th>Type</th><th>Score</th><th>Risque</th><th>Priorité</th><th>Source</th><th>Résumé</th></tr></thead><tbody>
    ${data.items.map((a) => `<tr><td>${esc(a.created_at)}</td><td>${esc(a.actor_email)}</td><td>${esc(a.phone_mask)}</td><td>${esc(a.kind)}</td><td>${a.score ?? "—"}</td><td>${a.risk_level ? pill(a.risk_level, a.risk_level) : "—"}</td><td>${esc(a.priority || "—")}</td><td>${a.cold_start ? "RULES" : esc(a.prediction_source)} ${a.retention_probability == null ? "" : "· " + Math.round(a.retention_probability * 100) + "%"}</td><td>${esc(a.summary)}</td></tr>`).join("") || `<tr><td colspan="9" class="fine">Aucune analyse enregistrée pour l'instant. Une recherche en créera.</td></tr>`}
  </tbody></table><div class="pager"><button class="btn btn-ghost btn-sm" id="hp"${page <= 1 ? " disabled" : ""}>Précédent</button><span>${page}</span><button class="btn btn-ghost btn-sm" id="hn">Suivant</button></div></section>`;
  $("#hp").onclick = () => { location.hash = "#/history?page=" + (page - 1); };
  $("#hn").onclick = () => { location.hash = "#/history?page=" + (page + 1); };
}

async function renderAdmin(view, path) {
  if (me.role !== "ADMIN") { view.innerHTML = `<div class="card-dark">Accès administrateur requis.</div>`; return; }
  if (path === "/admin/stats") return renderAdminStats(view);
  setGreet("Administration", "Boutiques, comptes, paramètres autorisés du moteur, journal.");
  const [shops, users, settings, audit] = await Promise.all([
    api("/admin/boutiques"), api("/admin/users"), api("/admin/settings"), api("/admin/audit"),
  ]);
  const fields = Object.entries(settings.values);
  view.innerHTML = `
    <div class="row g-3">
      <section class="col-lg-7 card-dark"><h2 class="h5">Boutiques</h2>
        <div class="table-wrap"><table class="data"><thead><tr><th>Nom</th><th>Lieu</th><th>Commandes</th><th></th></tr></thead><tbody>
          ${shops.items.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.city)}, ${esc(b.governorate)}</td><td>${b.orders}</td>
            <td><button class="btn btn-ghost btn-sm" data-shop="${b.id}" data-active="${b.active ? "0" : "1"}">${b.active ? "Désactiver" : "Activer"}</button></td></tr>`).join("")}
        </tbody></table></div>
        <form id="new-shop" class="row g-2 mt-2">
          <div class="col-md-4"><input class="form-control" name="name" placeholder="Nom" required></div>
          <div class="col-md-3"><input class="form-control" name="governorate" placeholder="Gouvernorat" required></div>
          <div class="col-md-3"><input class="form-control" name="city" placeholder="Ville" required></div>
          <div class="col-md-8"><input class="form-control" name="address" placeholder="Adresse fictive" required></div>
          <div class="col-md-4"><button class="btn btn-accent w-100">Ajouter</button></div>
        </form>
      </section>
      <section class="col-lg-5 card-dark"><h2 class="h5">Comptes</h2>
        <div class="table-wrap" style="max-height:280px;overflow:auto"><table class="data"><tbody>
          ${users.items.map((u) => `<tr><td>${esc(u.full_name)}<div class="fine">${esc(u.email)} · ${esc(u.role)} · ${esc(u.shop || "")}</div></td>
            <td><button class="btn btn-ghost btn-sm" data-user="${u.id}" data-active="${u.active ? "0" : "1"}">${u.active ? "Désactiver" : "Activer"}</button></td></tr>`).join("")}
        </tbody></table></div>
        <form id="new-user" class="mt-2">
          <input class="form-control mb-1" name="full_name" placeholder="Nom" required>
          <input class="form-control mb-1" name="email" type="email" placeholder="E-mail" required>
          <input class="form-control mb-1" name="password" type="text" placeholder="Mot de passe (8+)" required>
          <div class="d-flex gap-2"><select class="form-select" name="role"><option>SHOP</option><option>ADMIN</option></select>
          <input class="form-control" name="boutique_id" type="number" placeholder="ID boutique"></div>
          <button class="btn btn-accent mt-2">Créer le compte</button>
        </form>
      </section>
      <section class="col-lg-7 card-dark"><h2 class="h5">Paramètres autorisés</h2>
        <p class="fine">${esc(settings.note)}</p>
        <form id="settings-form" class="row g-2">
          ${fields.map(([k, v]) => `<div class="col-md-4"><label class="form-label fine">${esc(k)}</label><input class="form-control" name="${esc(k)}" value="${esc(v)}"></div>`).join("")}
          <div class="col-12 d-flex gap-2"><button class="btn btn-accent" type="submit">Enregistrer</button><button class="btn btn-ghost" type="button" id="reset-settings">Restaurer le Sprint 1</button></div>
        </form>
      </section>
      <section class="col-lg-5 card-dark"><h2 class="h5">Journal</h2>
        <div style="max-height:360px;overflow:auto"><table class="data"><tbody>
          ${audit.items.map((a) => `<tr><td class="fine">${esc(a.created_at)}<br>${esc(a.actor_email)} · ${esc(a.action)}</td><td>${esc(a.details)}</td></tr>`).join("")}
        </tbody></table></div>
      </section>
    </div>`;
  view.querySelectorAll("[data-shop]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/admin/boutiques/${b.dataset.shop}?active=${b.dataset.active === "1" ? "true" : "false"}`, { method: "PATCH" });
    route();
  }));
  view.querySelectorAll("[data-user]").forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/admin/users/${b.dataset.user}?active=${b.dataset.active === "1" ? "true" : "false"}`, { method: "PATCH" });
      route();
    } catch (err) { toast(err.message, "err"); }
  }));
  $("#new-shop").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("/admin/boutiques", { method: "POST", body: Object.fromEntries(fd.entries()) });
      toast("Boutique créée."); route();
    } catch (err) { toast(err.message, "err"); }
  });
  $("#new-user").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    body.boutique_id = body.boutique_id ? Number(body.boutique_id) : null;
    try { await api("/admin/users", { method: "POST", body }); toast("Compte créé."); route(); }
    catch (err) { toast(err.message, "err"); }
  });
  $("#settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = {};
    for (const [k, v] of fd.entries()) payload[k] = v.includes(".") ? Number(v) : Number(v);
    try { await api("/admin/settings", { method: "PUT", body: payload }); toast("Paramètres appliqués au moteur en mémoire."); }
    catch (err) { toast(err.message, "err"); }
  });
  $("#reset-settings").addEventListener("click", async () => {
    await api("/admin/settings/reset", { method: "POST" });
    toast("Constantes du Sprint 1 restaurées.");
    route();
  });
}

async function renderAdminStats(view) {
  setGreet("Statistiques globales", "Chaque moyenne de score est recalculée par le moteur sur les commandes fictives. Le premier affichage peut prendre quelques secondes.");
  view.innerHTML = `<div class="fine">Calcul des scores de toutes les boutiques…</div>`;
  const data = await api("/admin/stats");
  const g = data.global;
  view.innerHTML = `
    <div class="grid-kpi mb-3">
      ${kpi("Commandes", esc(g.totals.orders), { html: `${g.totals.delivered} livrées · ${g.totals.refused} refusées · ${g.totals.not_collected} non récupérées` }, "bi-box")}
      ${kpi("Clients suivis", esc(g.customers), { html: `cold start ${g.cold_start_pct} %` }, "bi-people")}
      ${kpi("Score moyen", `${g.mean_score ?? "—"}<small>/100</small>`, { html: "live" }, "bi-shield")}
      ${kpi("Rétention ML", g.mean_retention == null ? "—" : g.mean_retention + "%", { html: esc(g.model_version || "hors cold start") }, "bi-activity")}
    </div>
    <section class="card-dark table-wrap"><table class="data"><thead><tr><th>Boutique</th><th>Lieu</th><th>Commandes</th><th>Clients</th><th>Score moyen</th><th>HIGH pending</th><th>Cold start</th><th>Répartition</th></tr></thead><tbody>
      ${data.boutiques.map((b) => `<tr><td>${esc(b.name)}${b.active ? "" : " · inactive"}</td><td>${esc(b.city)}, ${esc(b.governorate)}</td><td>${b.orders}</td><td>${b.customers}</td><td>${b.mean_score ?? "—"}</td><td>${b.high_priority_pending}</td><td>${b.cold_start_pct} %</td><td class="fine">L${b.risk.LOW} M${b.risk.MEDIUM} H${b.risk.HIGH}</td></tr>`).join("")}
    </tbody></table></section>`;
}

window.addEventListener("hashchange", () => { if (me) route(); });
boot();
