// Operator console: queue -> case -> reply. Text from merchants and the model is always set with
// textContent (never innerHTML). The token stays in sessionStorage for this tab only.
"use strict";

const $ = (id) => document.getElementById(id);
const KEY = "getnet.operator.token";
const PRIORITY = { urgent: "URGENTE", high: "alta", normal: "normal" };
const STATUS = { pending: "pendente", replying: "respondendo", resolved: "resolvido" };
const REASON = {
  charge_dispute: "contestação de cobrança",
  fraud_suspected: "suspeita de fraude",
  customer_request: "pedido de atendimento humano",
  unresolved: "não resolvido",
  sensitive: "assunto sensível",
};
const AUDIT = {
  created: "transbordo aberto",
  notified: "aviso enviado",
  sla_breached: "prazo vencido, prioridade elevada",
  reply_blocked: "mensagem do operador bloqueada",
  replied: "operador respondeu",
  resolved: "lojista recebeu a resposta",
  resume_failed: "falha ao retomar (volta para a fila)",
};
let current = null;
let memoryToken = null; // used when sessionStorage is blocked
let timer = null;

function token() {
  try { return sessionStorage.getItem(KEY) || memoryToken; } catch { return memoryToken; }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json" },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body?.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.code = body?.error?.code;
    throw error;
  }
  return body;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function since(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function deadline(h) {
  if (h.status !== "pending") return null;
  if (!h.due_at) return el("span", "prazo vencido", "late");
  const left = Math.round((new Date(h.due_at).getTime() - Date.now()) / 60000);
  return left < 0 ? el("span", `vencido há ${-left} min`, "late") : el("span", `prazo em ${left} min`);
}

async function loadQueue() {
  const list = $("queue");
  try {
    const items = await api(`/operator/handoffs?status=${encodeURIComponent($("status").value)}`);
    list.replaceChildren();
    $("queue-empty").hidden = items.length > 0;
    for (const h of items) {
      const li = el("li");
      li.tabIndex = 0;
      li.dataset.id = h.id;
      if (current === h.id) li.classList.add("active");
      const top = el("div", null, "row");
      top.append(el("strong", h.id), el("span", PRIORITY[h.priority] || h.priority, `badge p-${h.priority}`));
      const meta = el("div", `${REASON[h.reason] || h.reason} · ${h.merchant_id} · esperando ${since(h.created_at)}`, "small muted");
      li.append(top, meta);
      const due = deadline(h);
      if (due) {
        const line = el("div", null, "small");
        line.append(due);
        li.append(line);
      }
      li.addEventListener("click", () => openCase(h.id));
      li.addEventListener("keydown", (e) => { if (e.key === "Enter") openCase(h.id); });
      list.append(li);
    }
  } catch (error) {
    if (error.status === 401 || error.status === 403) return logout(error.message);
  }
}

async function openCase(id) {
  current = id;
  history.replaceState(null, "", `#${id}`);
  for (const li of $("queue").children) li.classList.toggle("active", li.dataset.id === id);
  let c;
  try {
    c = await api(`/operator/handoffs/${encodeURIComponent(id)}`);
  } catch (error) {
    current = null;
    history.replaceState(null, "", location.pathname);
    $("case-empty").textContent = `Não foi possível abrir ${id}: ${error.message}`;
    $("case-empty").hidden = false;
    $("case-body").hidden = true;
    return;
  }
  $("case-empty").hidden = true;
  $("case-body").hidden = false;
  $("case-title").textContent = `${c.id} · ${REASON[c.reason] || c.reason}`;
  const badge = $("case-priority");
  badge.textContent = PRIORITY[c.priority] || c.priority;
  badge.className = `badge p-${c.priority}`;
  const due = c.due_at && c.status === "pending" ? ` · prazo ${new Date(c.due_at).toLocaleTimeString("pt-BR")}` : "";
  $("case-meta").textContent = `Lojista ${c.merchant_id} · aberto há ${since(c.created_at)} · ${STATUS[c.status] || c.status}${due}`;
  $("case-summary").textContent = c.summary;

  const facts = $("facts");
  facts.replaceChildren();
  $("facts-empty").hidden = c.facts.length > 0;
  for (const f of c.facts) {
    const li = el("li");
    li.append(el("strong", f.tool), el("pre", f.result));
    facts.append(li);
  }

  const conversation = $("conversation");
  conversation.replaceChildren();
  for (const turn of c.conversation) {
    const merchant = el("li");
    merchant.append(el("div", "Lojista", "who"), el("p", turn.merchant));
    conversation.append(merchant);
    if (turn.assistant) {
      const assistant = el("li");
      assistant.append(el("div", "Assistente", "who"), el("p", turn.assistant));
      conversation.append(assistant);
    }
  }

  $("reply-box").hidden = c.status !== "pending";
  $("case-final").textContent = c.final_answer || "Ainda sem resposta final.";
  $("reply-result").textContent = "";

  const audit = $("audit");
  audit.replaceChildren();
  for (const a of c.audit) {
    const d = a.detail || {};
    const extra = a.kind === "notified" ? ` (${d.channel}${d.delivered ? "" : ", falhou"})`
      : a.kind === "reply_blocked" ? ` (${d.category})`
      : a.kind === "replied" ? ` (${d.action}): ${d.message}` : "";
    audit.append(el("li", `${new Date(a.at).toLocaleTimeString("pt-BR")} · ${AUDIT[a.kind] || a.kind} · ${a.actor}${extra}`));
  }
}

async function sendReply(event) {
  event.preventDefault();
  if (!current) return;
  const button = $("send");
  const result = $("reply-result");
  button.disabled = true;
  result.className = "";
  result.textContent = "Enviando e retomando a conversa…";
  try {
    const r = await api(`/operator/handoffs/${encodeURIComponent(current)}/reply`, {
      method: "POST",
      body: JSON.stringify({ action: $("action").value, message: $("message").value }),
    });
    result.className = "ok";
    result.textContent = "Enviado. O lojista recebeu a resposta abaixo.";
    $("message").value = "";
    await openCase(current);
    $("case-final").textContent = r.answer;
  } catch (error) {
    result.className = "fail";
    result.textContent = error.code === "operator_message_blocked"
      ? "Bloqueada pelo filtro de segurança. Nada foi enviado ao lojista."
      : error.status === 409 ? "Este caso já foi respondido." : `Falhou: ${error.message}`;
    if (current) await openCase(current);
  } finally {
    button.disabled = false;
    loadQueue();
  }
}

async function start() {
  try {
    const me = await api("/me");
    if (!me.scopes.includes("operator")) throw new Error("Este token não tem o escopo operator.");
    $("who").textContent = me.sub;
  } catch (error) {
    return logout(error.message);
  }
  $("login").hidden = true;
  $("app").hidden = false;
  $("logout").hidden = false;
  await loadQueue();
  const fromHash = location.hash.slice(1);
  if (/^H-[0-9A-F]{6}$/.test(fromHash)) openCase(fromHash);
  clearInterval(timer);
  timer = setInterval(loadQueue, 10000);
}

function logout(message) {
  memoryToken = null;
  try { sessionStorage.removeItem(KEY); } catch { /* storage blocked */ }
  clearInterval(timer);
  $("app").hidden = true;
  $("logout").hidden = true;
  $("login").hidden = false;
  $("who").textContent = "";
  $("login-error").textContent = typeof message === "string" ? message : "";
}

document.addEventListener("DOMContentLoaded", () => {
  $("login-form").addEventListener("submit", (event) => {
    event.preventDefault();
    memoryToken = $("token").value.trim();
    try { sessionStorage.setItem(KEY, memoryToken); } catch { /* storage blocked */ }
    $("token").value = "";
    start();
  });
  $("logout").addEventListener("click", () => logout(""));
  $("status").addEventListener("change", loadQueue);
  $("reply-form").addEventListener("submit", sendReply);
  if (token()) start();
});
