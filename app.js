"use strict";
const M = Modelo,
  $ = (s) => document.querySelector(s);
const ICONS = {
  overview: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  ranking: "M4 19V12h4v7M10 19V5h4v14M16 19V9h4v10",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  wallet:
    "M20 8V5H5a3 3 0 0 0 0 6h16v9H5a3 3 0 0 1-3-3V8M21 12h-6v5h6M17 14.5h.1",
  activity: "M2 12h4l3-8 5 16 3-8h5",
  info: "M12 8h.01M12 11v5M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  share: "M12 16V3M7 8l5-5 5 5M5 12v8h14v-8",
  download: "M12 3v12M7 10l5 5 5-5M5 16v5h14v-5",
  moon: "M21 13a9 9 0 0 1-10-10 9 9 0 1 0 10 10",
  close: "M6 6l12 12M6 18L18 6",
  arrow: "M5 15l6-6 4 4 5-7M15 6h5v5",
};
const icon = (name) =>
  `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name] || ICONS.info}"/></svg>`;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }),
  decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const brl = (v) => money.format(Number(v || 0)),
  short = (v) =>
    Math.abs(v) >= 1e6
      ? "R$ " + decimal.format(v / 1e6) + " mi"
      : Math.abs(v) >= 1000
        ? "R$ " + decimal.format(v / 1000) + " mil"
        : brl(v);
const pct = (v, t) =>
  !t
    ? "0%"
    : v > 0 && (v / t) * 100 < 0.1
      ? "< 0,1%"
      : decimal.format((v / t) * 100) + "%";
const stamp = (s) =>
  new Date(s).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
const shortDate = (s) =>
  s?.slice(0, 10).split("-").reverse().slice(0, 2).join("/") || "—";
const FONTES = [
  ["fundoEspecial", "Fundo Eleitoral (FEFC)", "--fefc"],
  ["fundoPartidario", "Fundo Partidário", "--fundo"],
  ["outros", "Outros recursos", "--priv"],
  ["roni", "Origem não identificada", "--roni"],
  ["estimavel", "Bens e serviços estimáveis", "--estim"],
];
const NATUREZAS = [
  ["partidos", "Repasses de partidos"],
  ["pessoaFisica", "Pessoas físicas"],
  ["outrosCandidatos", "Outros candidatos"],
  ["proprios", "Recursos próprios"],
  ["financiamentoColetivo", "Financiamento coletivo"],
  ["internet", "Pela internet"],
  ["roni", "Origem não identificada"],
  ["pessoaJuridica", "Pessoas jurídicas"],
  ["comercializacao", "Comercialização"],
  ["aplicacoes", "Aplicações financeiras"],
  ["bens", "Bens móveis e imóveis"],
];
const LABELS = {
  total: "Arrecadação líquida",
  fundos: "Fundos públicos",
  fefc: "Fundo Eleitoral",
  fp: "Fundo Partidário",
  outros: "Outros recursos",
  despesas: "Despesas contratadas",
  pagas: "Despesas pagas",
  nome: "Arrecadação líquida",
};
const VIEWS = [
  "candidatos",
  "visao-geral",
  "doadores",
  "despesas",
  "alteracoes",
  "metodologia",
];
const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
let dados = null,
  agregados = null,
  historico = [],
  correcoes = [],
  current = [],
  loading = false,
  lastError = false,
  activeId = null,
  detailTab = "receitas",
  activeDetail = null,
  detailSort = "valor",
  modalTrigger = null,
  view = "candidatos",
  page = 1,
  donorLimit = 30,
  supplierLimit = 24,
  modalEpoch = 0,
  toastTimer;
const detalhes = new Map(),
  filtro = { cargo: 0, partido: "", busca: "", ordem: "total" },
  PAGE_SIZE = 25;
function hydrateURL() {
  const p = new URLSearchParams(location.search);
  filtro.cargo = [6, 7].includes(+p.get("cargo")) ? +p.get("cargo") : 0;
  filtro.partido = p.get("partido") || "";
  filtro.busca = p.get("q") || "";
  filtro.ordem = Object.hasOwn(LABELS, p.get("ordem"))
    ? p.get("ordem")
    : "total";
  view = VIEWS.includes(p.get("aba")) ? p.get("aba") : "candidatos";
}
function updateURL() {
  const u = new URL(location.href);
  ["cargo", "partido", "q", "ordem", "aba", "candidato"].forEach((k) =>
    u.searchParams.delete(k),
  );
  if (filtro.cargo) u.searchParams.set("cargo", filtro.cargo);
  if (filtro.partido) u.searchParams.set("partido", filtro.partido);
  if (filtro.busca) u.searchParams.set("q", filtro.busca);
  if (filtro.ordem !== "total") u.searchParams.set("ordem", filtro.ordem);
  if (view !== "candidatos") u.searchParams.set("aba", view);
  if (activeId) u.searchParams.set("candidato", activeId);
  history.replaceState(null, "", u);
}
function doc(d) {
  const n = String(d || "").replace(/\D/g, "");
  if (n.length === 11)
    return "CPF " + n.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  if (n.length === 14)
    return (
      "CNPJ " +
      n.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
    );
  return esc(d || "");
}
function avatar(c) {
  const initials = c.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("");
  const photo = M.safeURL(c.foto);
  return `<span class="avatar" aria-hidden="true">${esc(initials)}${photo ? `<img src="${esc(photo)}" loading="lazy" decoding="async" alt="">` : ""}</span>`;
}
document.addEventListener(
  "error",
  (e) => {
    if (e.target instanceof HTMLImageElement) e.target.remove();
  },
  true,
);
const empty = (heading, text = "") =>
  `<div class="empty"><strong>${esc(heading)}</strong>${esc(text)}</div>`;
function resourceBase(data = dados) {
  const b = data?.arquivosBase || "";
  if (b && !/^coletas\/[a-zA-Z0-9_-]+\/$/.test(b))
    throw new Error("Caminho de dados inválido");
  return b;
}
async function json(path) {
  const response = await fetch(
    path + (path.includes("?") ? "&" : "?") + "t=" + Date.now(),
    { cache: "no-store", signal: AbortSignal.timeout(25000) },
  );
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}
async function carregar(force = false) {
  if (loading) return;
  loading = true;
  try {
    const next = await json("dados.json");
    if (!Array.isArray(next.candidatos) || !next.candidatos.length)
      throw new Error("Sem candidatos");
    if (
      dados?.atualizadoEm === next.atualizadoEm &&
      dados?.arquivosBase === next.arquivosBase &&
      JSON.stringify(dados?.ultimaTentativa) ===
        JSON.stringify(next.ultimaTentativa) &&
      !force
    ) {
      lastError = false;
      $("#load-error").hidden = true;
      $("#retry").hidden = true;
      renderStatus();
      return;
    }
    const base = resourceBase(next);
    const [ag, h, c] = await Promise.all([
      json(base + "agregados.json"),
      json(base + "historico.json"),
      json(base + "correcoes.json"),
    ]);
    if (!ag || !Array.isArray(h) || !Array.isArray(c))
      throw new Error("Dados incompletos");
    // Trocar o conjunto apenas quando todos os arquivos da mesma publicação chegaram.
    dados = next;
    agregados = ag;
    historico = h;
    correcoes = c;
    lastError = false;
    detalhes.clear();
    $("#load-error").hidden = true;
    $("#retry").hidden = true;
    $("#dashboard").setAttribute("aria-busy", "false");
    mountParties();
    render(false);
    if (activeId) abrirModal(activeId, false);
    else {
      const id = new URLSearchParams(location.search).get("candidato");
      if (id && dados.candidatos.some((x) => x.id === id))
        abrirModal(id, false);
    }
  } catch (error) {
    lastError = true;
    $("#retry").hidden = false;
    $("#load-error").hidden = false;
    $("#load-error").textContent = dados
      ? "Não foi possível buscar a publicação mais recente. Exibindo a última coleta carregada, com seu horário original."
      : "Não foi possível carregar o painel. Tente novamente em instantes.";
    $("#dashboard").setAttribute("aria-busy", "false");
    renderStatus();
  } finally {
    loading = false;
  }
}
function mountParties() {
  const counts = {};
  dados.candidatos.forEach(
    (c) => (counts[c.partido] = (counts[c.partido] || 0) + 1),
  );
  const names = Object.keys(counts).sort((a, b) => a.localeCompare(b, "pt-BR"));
  if (filtro.partido && !names.includes(filtro.partido)) filtro.partido = "";
  $("#partido").innerHTML =
    '<option value="">Todos os partidos</option>' +
    names
      .map((p) => `<option value="${esc(p)}">${esc(p)} (${counts[p]})</option>`)
      .join("");
}
function renderStatus() {
  if (!dados) {
    $("#status").textContent = lastError
      ? "Não foi possível carregar"
      : "Carregando dados…";
    return;
  }
  const age = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(dados.atualizadoEm)) / 60000),
  );
  const stale =
    age >= 180 || lastError || dados.ultimaTentativa?.status === "falhou";
  $("#status").textContent = stale
    ? "Última coleta disponível"
    : age < 1
      ? "Coleta concluída agora"
      : `Coleta há ${age < 60 ? age + " min" : Math.floor(age / 60) + " h"}`;
  $("#status-date").textContent =
    stamp(dados.atualizadoEm) +
    " · horário de Brasília" +
    (dados.ultimaTentativa?.status === "falhou"
      ? " · Nova coleta não concluída"
      : "");
  $("#status-dot").style.background = stale ? "var(--orange)" : "var(--green)";
  $(".status-line").classList.toggle("stale", stale);
  $("#rodape-atualizacao").textContent =
    "Última coleta concluída: " + stamp(dados.atualizadoEm) + " (Brasília)";
}
function syncFilters() {
  $("#partido").value = filtro.partido;
  $("#busca").value = filtro.busca;
  $("#ordem").value = filtro.ordem;
  $("#btn-novo").classList.toggle("on", filtro.partido === "NOVO");
  $("#btn-novo").setAttribute("aria-pressed", filtro.partido === "NOVO");
  document.querySelectorAll("[data-cargo]").forEach((b) => {
    const on = +b.dataset.cargo === filtro.cargo;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
  });
  $("#selo").textContent =
    (filtro.partido || "Todos os partidos") +
    " · " +
    (filtro.cargo === 6
      ? "Deputado federal"
      : filtro.cargo === 7
        ? "Deputado estadual"
        : "Todos os cargos");
  $("#clear-filters").hidden =
    !filtro.cargo && !filtro.partido && !filtro.busca;
  $("#filter-count").textContent =
    `${current.length} de ${dados.candidatos.length} candidatos`;
}
function render(save = true) {
  if (!dados) return;
  current = M.filter(dados.candidatos, filtro);
  syncFilters();
  renderStatus();
  renderView();
  if (save) updateURL();
}
function metricCard(label, value, note, ico, featured = false, exact = false) {
  return `<article class="metric${featured ? " featured" : ""}"><div class="metric-label">${label}${icon(ico)}</div><div class="metric-value" title="${exact ? esc(brl(value)) : ""}">${exact ? short(value) : value}</div><div class="metric-note">${note}${exact ? `<span class="exact">${brl(value)}</span>` : ""}</div></article>`;
}
function prior() {
  const day = dados.atualizadoEm.slice(0, 10);
  return [...historico].reverse().find((p) => p.data < day);
}
function renderSummary() {
  const total = M.sum(current, M.net),
    funds = M.sum(current, M.publicFunds),
    spent = M.sum(current, (c) => c.despesas.contratadas),
    returns = M.sum(current, (c) => c.devolvido || 0),
    paid = M.sum(current, (c) => c.despesas.pagas);
  const p = prior(),
    diffs = current.map((c) => M.delta(c, p));
  const delta =
    current.length && diffs.every((x) => x !== null)
      ? M.sum(diffs, (x) => x)
      : null;
  const note =
    delta === null
      ? "Após descontar devoluções"
      : `${delta >= 0 ? "+" : ""}${brl(delta)} desde ${shortDate(p.data)}`;
  $("#resumo").innerHTML =
    metricCard("Arrecadação líquida", total, note, "arrow", true, true) +
    metricCard(
      "Fundos públicos",
      funds,
      `${pct(funds, total)} da arrecadação`,
      "wallet",
      false,
      true,
    ) +
    metricCard(
      "Despesas contratadas",
      spent,
      `${short(paid)} pagos`,
      "activity",
      false,
      true,
    ) +
    metricCard(
      "Candidatos no recorte",
      String(current.length),
      `${current.filter((c) => M.net(c) > 0).length} com receita declarada`,
      "users",
    );
  $("#resumo").setAttribute(
    "aria-label",
    `Resumo do recorte; arrecadação líquida ${brl(total)}; devoluções ${brl(returns)}`,
  );
}
function sources(list) {
  return FONTES.map(([key, name, color]) => ({
    key,
    name,
    color,
    value: M.sum(list, (c) => c.origem[key] || 0),
  }));
}
function bar(parts) {
  const total = M.sum(parts, (x) => x.value);
  return parts
    .filter((x) => x.value > 0)
    .map(
      (x) =>
        `<span style="width:${total ? (x.value / total) * 100 : 0}%;background:var(${x.color})" title="${esc(x.name)}: ${brl(x.value)}"></span>`,
    )
    .join("");
}
function legend(parts) {
  const total = M.sum(parts, (x) => x.value);
  return parts
    .filter((x) => x.value > 0)
    .map(
      (x) =>
        `<div class="legend-item"><i class="legend-dot" style="background:var(${x.color})"></i><div><span class="legend-name">${x.name}</span><span class="legend-amount">${brl(x.value)}<span class="legend-pct">${pct(x.value, total)}</span></span></div></div>`,
    )
    .join("");
}
function renderSources() {
  const parts = sources(current);
  $("#barra-global").innerHTML = bar(parts);
  $("#legenda-global").innerHTML =
    legend(parts) || '<p class="muted">Sem receitas neste recorte.</p>';
}
function renderTrend() {
  const all = !filtro.cargo && !filtro.partido && !filtro.busca;
  const points = historico
    .filter((p) => p.data >= "2026-08-29")
    .slice(-14)
    .map((p) => {
      if (all) return { date: p.data, total: p.total };
      const known =
        current.length &&
        current.every((c) => Object.hasOwn(p.porCandidato || {}, c.id));
      return known
        ? { date: p.data, total: M.sum(current, (c) => p.porCandidato[c.id]) }
        : null;
    })
    .filter(Boolean);
  $("#trend-period").textContent = points.length
    ? `${points.length} registros`
    : "Em formação";
  $("#trend-note").textContent =
    "Receita bruta publicada em cada dia. A cobertura pode variar; o histórico não desconta devoluções.";
  if (points.length < 2) {
    $("#trend").innerHTML =
      '<p class="trend-empty">O histórico deste recorte precisa de pelo menos dois dias comparáveis.</p>';
    return;
  }
  const w = 460,
    h = 106,
    max = Math.max(...points.map((p) => p.total), 1),
    x = (i) => 8 + (i / (points.length - 1)) * (w - 16),
    y = (v) => 12 + (1 - v / max) * (h - 22),
    path = points
      .map(
        (p, i) =>
          `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(p.total).toFixed(1)}`,
      )
      .join(" "),
    last = points.at(-1);
  $("#trend").innerHTML =
    `<div class="trend-value">${short(last.total)}</div><svg class="trend-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Evolução da receita bruta: de ${brl(points[0].total)} em ${shortDate(points[0].date)} a ${brl(last.total)} em ${shortDate(last.date)}"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--fefc)" stop-opacity=".16"/><stop offset="100%" stop-color="var(--fefc)" stop-opacity="0"/></linearGradient></defs>${[0.25, 0.5, 0.75].map((f) => `<line x1="0" x2="${w}" y1="${f * h}" y2="${f * h}" stroke="var(--border)" stroke-dasharray="3 5"/>`).join("")}<path d="${path} L ${x(points.length - 1)} ${h} L 8 ${h} Z" fill="url(#chart-fill)"/><path d="${path}" stroke="var(--fefc)" stroke-width="2.4" fill="none" vector-effect="non-scaling-stroke"/>${points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.total)}" r="${i === points.length - 1 ? 3 : 2}" fill="var(--fefc)"><title>${shortDate(p.date)}: ${brl(p.total)}</title></circle>`).join("")}</svg><div class="trend-axis"><span>${shortDate(points[0].date)}</span><span>${shortDate(last.date)}</span></div><details class="trend-detail"><summary>Ver valores por dia</summary><table><tbody>${points.map((p) => `<tr><td>${shortDate(p.date)}</td><td>${brl(p.total)}</td></tr>`).join("")}</tbody></table></details>`;
}
function renderView() {
  document.querySelectorAll("[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    if (b.dataset.view === view) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  VIEWS.forEach((v) => ($("#view-" + v).hidden = v !== view));
  if (!dados) return;
  const total = M.sum(current, M.net);
  $("#correction-count").textContent = correcoes.length || "";
  if (view === "candidatos") renderRanking();
  if (view === "visao-geral") {
    renderSummary();
    renderSources();
    renderTrend();
  }
  if (view === "doadores") renderDonors(total);
  if (view === "despesas") renderExpenses();
  if (view === "alteracoes") renderCorrections();
}
function recentRevenueRow(c, p) {
  const change = M.recentRevenue(c, p);
  if (!change) {
    return '<div class="row-recent neutral" title="Não há valor anterior registrado para comparar este candidato.">Sem base anterior</div>';
  }
  const basis = change.basis === "liquida" ? "líquida" : "bruta";
  const period = `${shortDate(p.data)}${p.hora ? " às " + p.hora : ""}`;
  const title = `Variação da arrecadação ${basis} desde a coleta de ${period} (Brasília). Pode incluir novas receitas, devoluções e retificações, conforme a base comparada.`;
  const color =
    change.value > 0 ? "positive" : change.value < 0 ? "negative" : "neutral";
  const amount =
    change.value === 0
      ? "Sem variação"
      : `${change.value > 0 ? "+" : "−"}${brl(Math.abs(change.value))}`;
  return `<div class="row-recent ${color}" title="${esc(title)}">${amount}</div><div class="row-recent-period">Arrecadação ${basis}<br>desde ${shortDate(p.data)}</div>`;
}
function renderRanking() {
  const maxPage = Math.max(1, Math.ceil(current.length / PAGE_SIZE));
  page = Math.min(page, maxPage);
  const list = current.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    p = prior();
  $("#metric-title").textContent = LABELS[filtro.ordem];
  $("#ranking-sub").textContent =
    filtro.ordem === "nome"
      ? "Em ordem alfabética"
      : `Ordenado por ${LABELS[filtro.ordem].toLocaleLowerCase("pt-BR")}`;
  $("#lista").innerHTML =
    list
      .map((c, i) => {
        const total = M.net(c),
          pos = (page - 1) * PAGE_SIZE + i + 1,
          value = M.metric(c, filtro.ordem);
        return `<tr data-id="${c.id}" data-open="${c.id}"><td class="rank${pos <= 3 ? " top" : ""}">${pos}</td><td><button class="candidate-open" data-open="${c.id}" aria-label="Ver contas de ${esc(c.nome)}">${avatar(c)}<span class="candidate-info"><span class="candidate-name">${esc(c.nome)}</span><span class="candidate-meta"><span class="party-tag${c.partido === "NOVO" ? " novo" : ""}">${esc(c.partido)}</span><span>${c.numero}</span><span>· ${c.cargo === 6 ? "Federal" : "Estadual"}</span></span></span></button></td><td class="source-cell"><div class="mini-bar" aria-hidden="true">${bar(sources([c]))}</div><div class="mini-note">${total ? pct(M.publicFunds(c), total) + " de fundos públicos" : c.temContas ? "Sem receita declarada" : "Sem prestação disponível"}</div></td><td class="money"><div class="row-value" data-label="${LABELS[filtro.ordem]}">${c.temContas ? brl(value) : "—"}</div>${c.temContas ? recentRevenueRow(c, p) : ""}<div class="row-sub">${c.temContas ? (c.qtdLancamentos ?? c.qtdDoacoes) + " lançamentos" : "Sem prestação"}</div></td><td class="chevron-cell"><span class="chevron" aria-hidden="true">›</span></td></tr>`;
      })
      .join("") ||
    `<tr><td colspan="5">${empty("Nenhum candidato encontrado", "Tente outro nome, número ou partido.")}</td></tr>`;
  $("#page-info").textContent = current.length
    ? `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, current.length)} de ${current.length} candidatos`
    : "Nenhum resultado";
  $("#prev").disabled = page === 1;
  $("#next").disabled = page >= maxPage;
  $("#export").disabled = !current.length;
}
function entities(items, limit) {
  return items
    .slice(0, limit)
    .map(
      (e, i) =>
        `<div class="entity-row"><span class="rank">${i + 1}</span><div><div class="entity-name">${esc(e.nome || "Não informado")}${e.fcc ? '<span class="badge">Financiamento coletivo</span>' : ""}</div><div class="entity-meta">${doc(e.doc)} · ${e.ids.size} ${e.ids.size === 1 ? "candidato" : "candidatos"} · ${e.qtd} lançamentos</div></div><span class="entity-money" title="${esc(brl(e.valor))}">${brl(e.valor)}</span></div>`,
    )
    .join("");
}
function renderDonors(total) {
  $("#funding-summary").innerHTML = [
    ["partidos", "Repasses de partidos"],
    ["pessoaFisica", "Pessoas físicas"],
    ["outrosCandidatos", "Repasses de candidatos"],
  ]
    .map(([key, name]) => {
      const n = M.sum(current, (c) => c.receitas[key]);
      return metricCard(
        name,
        n,
        pct(n, total) + " da receita",
        "users",
        false,
        true,
      );
    })
    .join("");
  let list = M.aggregate(current, agregados, "doadores"),
    q = M.norm($("#donor-search").value);
  list = list.filter((e) => !q || M.norm(e.nome + " " + e.doc).includes(q));
  $("#doadores").innerHTML =
    entities(list, donorLimit) ||
    empty(
      "Nenhum doador neste recorte",
      "Mude os filtros ou a busca para consultar outros registros.",
    );
  $("#more-donors").hidden = list.length <= donorLimit;
}
function renderExpenses() {
  const contracted = M.sum(current, (c) => c.despesas.contratadas),
    paid = M.sum(current, (c) => c.despesas.pagas);
  $("#expense-metrics").innerHTML =
    metricCard(
      "Despesas contratadas",
      contracted,
      "Compromissos declarados",
      "wallet",
      false,
      true,
    ) +
    metricCard(
      "Despesas pagas",
      paid,
      "Pagamentos declarados",
      "activity",
      false,
      true,
    ) +
    metricCard(
      "Diferença contratadas − pagas",
      contracted - paid,
      "Valores informados na última coleta",
      "info",
      false,
      true,
    );
  let list = M.aggregate(current, agregados, "fornecedores"),
    q = M.norm($("#supplier-search").value);
  list = list.filter((e) => !q || M.norm(e.nome + " " + e.doc).includes(q));
  $("#fornecedores").innerHTML =
    entities(list, supplierLimit) || empty("Nenhum fornecedor neste recorte");
  $("#more-suppliers").hidden = list.length <= supplierLimit;
  const cat = new Map();
  current.forEach((c) =>
    Object.entries(agregados[c.id]?.categorias || {}).forEach(([k, v]) =>
      cat.set(k, (cat.get(k) || 0) + M.cent(v)),
    ),
  );
  const cats = [...cat]
    .map(([name, v]) => ({ name, value: v / 100 }))
    .sort((a, b) => b.value - a.value);
  $("#categorias").innerHTML =
    cats
      .map(
        (c) =>
          `<div class="category"><div class="category-head"><span>${esc(c.name)}</span><b>${brl(c.value)}</b></div><div class="category-track"><span style="width:${contracted ? (c.value / contracted) * 100 : 0}%"></span></div><p class="category-pct">${pct(c.value, contracted)} do contratado</p></div>`,
      )
      .join("") || empty("Nenhuma categoria declarada");
}
function receiptURL(prestador, entrega) {
  if (!/^\d+$/.test(String(prestador)) || !/^\d+$/.test(String(entrega)))
    return null;
  return `https://divulgacandcontas.tse.jus.br/divulga/rest/v1/prestador/consulta/receitas/20322002026/${prestador}/${entrega}/lista?pagina=1`;
}
function renderCorrections() {
  const ids = new Set(current.map((c) => c.id)),
    list = correcoes.filter((e) => ids.has(e.id)).slice(0, 60);
  $("#correcoes").innerHTML =
    list
      .map((e) => {
        const change = (e.totalDepois || 0) - (e.totalAntes || 0),
          before = receiptURL(e.idPrestador, e.entregaAntes),
          after = receiptURL(e.idPrestador, e.entregaDepois);
        return `<article class="correction"><div class="correction-head"><button data-open="${esc(e.id)}">${esc(e.nome)}</button><span class="party-tag">${esc(e.partido)}</span><time>${stamp(e.quando)}</time></div><div class="correction-total">${brl(e.totalAntes)} → ${brl(e.totalDepois)} <span class="${change < 0 ? "negative" : "positive"}">(${change >= 0 ? "+" : ""}${brl(change)})</span></div><p class="doc">Totais brutos nas duas coletas.</p><ul>${(e.alteracoes || []).map((a) => `<li>${esc(a.doador || "Lançamento sem nome preservado")}: ${brl(a.de)} → ${brl(a.para)}${a.doc ? ` · documento ${esc(a.doc)}` : ""}</li>`).join("")}${(e.removidos || []).map((a) => `<li>${esc(a.doador || "Lançamento sem nome preservado")}: ${brl(a.valor)} não aparece na coleta seguinte${a.doc ? ` · documento ${esc(a.doc)}` : ""}.</li>`).join("")}</ul><div class="links">${before ? `<a href="${before}" target="_blank" rel="noopener">Entrega anterior no TSE ↗</a> · ` : ""}${after ? `<a href="${after}" target="_blank" rel="noopener">Entrega seguinte no TSE ↗</a>` : ""}</div></article>`;
      })
      .join("") ||
    empty(
      "Nenhuma alteração registrada neste recorte",
      "O monitor compara coletas completas desde sua ativação. Isso não significa que nunca houve alterações.",
    );
}
function table(headers, rows, scroll = true) {
  return `<div${scroll ? ' class="scroll-table" tabindex="0" role="region" aria-label="Tabela de lançamentos"' : ""}><table class="detail-table"><thead><tr>${headers.map((h, i) => `<th scope="col"${h === "Data" ? ' class="date-cell"' : ""}>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}
function pairRow(label, value, sub = "") {
  return `<tr><td>${esc(label)}${sub ? `<div class="doc">${esc(sub)}</div>` : ""}</td><td>${brl(value)}</td></tr>`;
}
async function abrirModal(id, save = true) {
  const c = dados?.candidatos.find((x) => x.id === id);
  if (!c) return;
  const reopening = activeId === id && $("#modal").open;
  if (!$("#modal").open) modalTrigger = document.activeElement;
  activeId = id;
  activeDetail = null;
  detailTab = "receitas";
  detailSort = "valor";
  const epoch = ++modalEpoch,
    version = dados.atualizadoEm;
  const url = M.safeURL(c.urlTse);
  $("#modal-conteudo").innerHTML =
    `<div class="modal-header">${avatar(c)}<div><h2 id="modal-title">${esc(c.nome)}</h2><p>${esc(c.partido)} · ${c.numero} · ${esc(c.cargoNome)}</p><p>${esc(c.nomeCompleto || "")}</p></div><button class="icon-button close" id="close-modal" aria-label="Fechar detalhes">${icon("close")}</button></div><div class="modal-content"><div class="modal-meta"><span>Situação: ${esc(c.situacao || "Não informada")}</span><span>Prestação no TSE: ${esc(c.contasAtualizadas || "Não disponível")}</span><span>Coleta: ${stamp(dados.atualizadoEm)}</span></div><div class="modal-stats">${metricCard("Arrecadação líquida", M.net(c), "Bruto: " + brl(c.total), "arrow", false, true)}${metricCard("Fundos públicos", M.publicFunds(c), pct(M.publicFunds(c), M.net(c)) + " da receita", "wallet", false, true)}${metricCard("Despesas contratadas", c.despesas.contratadas, brl(c.despesas.pagas) + " pagos", "activity", false, true)}</div>${c.devolvido ? `<p class="notice">Foram declarados ${brl(c.devolvido)} em receitas devolvidas. A arrecadação líquida exibida já desconta esse valor.</p>` : ""}<div class="composition-bar" style="margin-left:0;margin-right:0" aria-hidden="true">${bar(sources([c]))}</div><div class="legend" style="margin-left:0;margin-right:0">${legend(sources([c]))}</div>${!c.temContas ? '<p class="notice">O TSE não disponibilizou uma prestação de contas para este candidato nesta coleta.</p>' : ""}<div class="detail-tabs" role="tablist" aria-label="Detalhes das contas"><button role="tab" id="tab-receitas" data-detail="receitas" class="on" aria-controls="detail-body" aria-selected="true">Doações</button><button role="tab" id="tab-despesas" data-detail="despesas" aria-controls="detail-body" aria-selected="false" tabindex="-1">Despesas</button><button role="tab" id="tab-entregas" data-detail="entregas" aria-controls="detail-body" aria-selected="false" tabindex="-1">Entregas</button></div><div id="detail-body" role="tabpanel" aria-labelledby="tab-receitas"><div class="empty">Carregando lançamentos…</div></div><div class="modal-links">${url ? `<a class="button primary" href="${esc(url)}" target="_blank" rel="noopener">Ver candidato no TSE ↗</a>` : ""}<button class="button secondary" id="share-candidate">${icon("share")}Compartilhar candidato</button>${(
      c.sites || []
    )
      .map(M.safeURL)
      .filter(Boolean)
      .map(
        (s) =>
          `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">${esc(new URL(s).hostname.replace(/^www\./, ""))} ↗</a>`,
      )
      .join("")}</div></div>`;
  if (!$("#modal").open) $("#modal").showModal();
  if (!reopening) $("#modal").scrollTop = 0;
  document.body.style.overflow = "hidden";
  $("#close-modal").onclick = fecharModal;
  $("#share-candidate").onclick = share;
  $("#close-modal").focus({ preventScroll: true });
  if (save) updateURL();
  try {
    let det = detalhes.get(id);
    if (!det) {
      det = await json(resourceBase() + `detalhe/${id}.json`);
      if (det.id !== id || det.atualizadoEm !== version)
        throw new Error("Detalhe pertence a outra coleta");
      detalhes.set(id, det);
    }
    if (
      activeId !== id ||
      modalEpoch !== epoch ||
      dados.atualizadoEm !== version ||
      !$("#modal").open
    )
      return;
    activeDetail = det;
    renderDetail();
  } catch {
    if (activeId !== id || modalEpoch !== epoch || !$("#modal").open) return;
    $("#detail-body").innerHTML = empty(
      "Os lançamentos não puderam ser carregados",
      "A publicação pode ter sido atualizada. Feche, atualize o painel e tente novamente; os valores acima continuam identificados pela data da coleta.",
    );
  }
}
function renderDetail() {
  const c = dados.candidatos.find((c) => c.id === activeId);
  if (!c) return;
  document.querySelectorAll("[data-detail]").forEach((b) => {
    const on = b.dataset.detail === detailTab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on);
    b.tabIndex = on ? 0 : -1;
  });
  $("#detail-body").setAttribute("aria-labelledby", "tab-" + detailTab);
  if (!activeDetail && detailTab !== "entregas") return;
  let html = "";
  if (detailTab === "receitas") {
    const r = activeDetail.receitas || [],
      date = (v) => {
        const m = String(v).match(/(\d{2})\/(\d{2})\/(\d{4})/);
        return m ? m[3] + m[2] + m[1] : String(v);
      };
    const sorted = [...r].sort((a, b) =>
      detailSort === "data"
        ? date(b.data).localeCompare(date(a.data))
        : b.valor - a.valor,
    );
    const campaignMap = new Map(
      dados.candidatos.map((c) => [c.cnpjCampanha, c]),
    );
    html = `<section class="modal-section"><div class="detail-heading"><h3>Doações uma a uma <span class="tag">${r.length}</span></h3><label><span class="sr-only">Ordenar doações</span><select id="detail-sort"><option value="valor">Maior valor</option><option value="data">Mais recentes</option></select></label></div>${
      r.length
        ? table(
            ["Data", "Doador e origem", "Valor"],
            sorted
              .map((x) => {
                const sender = campaignMap.get(x.cpfCnpj);
                return `<tr><td class="doc date-cell">${esc(x.data || "—")}</td><td class="description">${esc(x.doador || "Não informado")}${sender ? ` <span class="badge">Candidato · ${esc(sender.partido)}</span>` : ""}<div class="doc">${doc(x.cpfCnpj)} · ${esc(x.data || "")}</div><span class="source-pill">${esc(x.fonte || "Fonte não informada")}</span><div class="doc">${esc(x.especie || "")}${x.doc ? " · Documento " + esc(x.doc) : ""}${x.origBem ? "<br>Doador originário: " + esc(x.origBem) : ""}</div></td><td>${brl(x.valor)}</td></tr>`;
              })
              .join(""),
          )
        : empty("Nenhum lançamento de receita publicado")
    }</section><section class="modal-section"><h3>Quem entregou os recursos</h3><p class="panel-note">Natureza da receita. Essa classificação olha quem transferiu; a barra acima olha a fonte.</p>${table(
      ["Natureza", "Valor"],
      NATUREZAS.filter(([key]) => c.receitas[key] > 0)
        .map(([key, name]) => pairRow(name, c.receitas[key]))
        .join(""),
      false,
    )}</section>`;
  } else if (detailTab === "despesas") {
    const d = activeDetail.despesas || [];
    html = `<section class="modal-section"><h3>Resumo das despesas</h3>${table(["Descrição", "Valor"], pairRow("Contratadas", c.despesas.contratadas) + pairRow("Pagas", c.despesas.pagas) + pairRow("Limite de gastos informado pelo TSE", c.limiteGasto), false)}${c.despesas.contratadas > M.net(c) + 0.05 ? '<p class="notice">As despesas contratadas superam a receita líquida declarada nesta coleta. Essa diferença, isoladamente, não permite concluir se há irregularidade.</p>' : ""}</section><section class="modal-section"><h3>Despesas uma a uma <span class="tag">${d.length}</span></h3>${
      d.length
        ? table(
            ["Data", "Fornecedor e categoria", "Contratado"],
            [...d]
              .sort((a, b) => b.valor - a.valor)
              .map(
                (x) =>
                  `<tr><td class="doc date-cell">${esc(x.data || "—")}</td><td class="description">${esc(x.fornecedor || "Não informado")}<div class="doc">${doc(x.cpfCnpj)} · ${esc(x.data || "")}</div><span class="source-pill">${esc(x.categoria || "Categoria não informada")}</span><div class="doc">${esc(x.descricao || "")}${x.doc ? " · Documento " + esc(x.doc) : ""}</div></td><td>${brl(x.valor)}</td></tr>`,
              )
              .join(""),
          )
        : empty("Nenhuma despesa itemizada publicada")
    }</section>`;
  } else {
    html = `<section class="modal-section"><h3>Entregas de prestação de contas</h3><p class="panel-note">O detalhe financeiro mostra a última entrega disponível. As versões anteriores podem ser consultadas no TSE.</p>${c.entregas.length ? table(["Entrega", "Tipo"], c.entregas.map((e) => `<tr><td>${esc(e.data || "—")}</td><td>${esc(e.tipo)}${e.retificadora ? ' <span class="badge">Retificadora</span>' : ""}</td></tr>`).join("")) : empty("Nenhuma entrega disponível")}</section>`;
  }
  $("#detail-body").innerHTML = html;
  if ($("#detail-sort")) {
    $("#detail-sort").value = detailSort;
    $("#detail-sort").onchange = (e) => {
      detailSort = e.target.value;
      renderDetail();
    };
  }
}
function fecharModal() {
  if ($("#modal").open) $("#modal").close();
}
function afterClose() {
  activeId = null;
  activeDetail = null;
  modalEpoch++;
  document.body.style.overflow = "";
  updateURL();
  if (modalTrigger?.isConnected) modalTrigger.focus({ preventScroll: true });
}
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function share() {
  updateURL();
  try {
    await navigator.clipboard.writeText(location.href);
    toast("Link copiado com o recorte selecionado.");
  } catch {
    $("#toast").hidden = false;
    $("#toast").innerHTML =
      'Copie este link:<input aria-label="Link para compartilhar" readonly>';
    $("#toast input").value = location.href;
    $("#toast input").select();
  }
}
function exportCSV() {
  const headers = [
    "Candidato",
    "Partido",
    "Cargo",
    "Número",
    "Arrecadação líquida (R$)",
    "Bruto (R$)",
    "Devoluções (R$)",
    "FEFC (R$)",
    "Fundo Partidário (R$)",
    "Outros recursos (R$)",
    "RONI (R$)",
    "Estimáveis (R$)",
    "Contratadas (R$)",
    "Pagas (R$)",
    "Prestação disponível",
    "Data da prestação TSE",
    "Coleta (Brasília)",
    "Fonte",
  ];
  const fmt = (v) =>
    Number(v || 0)
      .toFixed(2)
      .replace(".", ",");
  const rows = current.map((c) => [
    c.nome,
    c.partido,
    c.cargoNome,
    c.numero,
    fmt(M.net(c)),
    fmt(c.total),
    fmt(c.devolvido),
    ...FONTES.map(([key]) => fmt(c.origem[key])),
    fmt(c.despesas.contratadas),
    fmt(c.despesas.pagas),
    c.temContas ? "Sim" : "Não",
    c.contasAtualizadas,
    stamp(dados.atualizadoEm),
    c.urlTse,
  ]);
  const text =
    "\uFEFF" +
    [headers, ...rows].map((r) => r.map(M.csvCell).join(";")).join("\r\n");
  const url = URL.createObjectURL(
      new Blob([text], { type: "text/csv;charset=utf-8;" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `ranking-sc-${filtro.partido || "todos"}-${dados.atualizadoEm.slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Ranking exportado com o recorte selecionado.");
}
function setTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $('meta[name="theme-color"]').content = dark ? "#12191d" : "#f6f7f9";
  $("#theme").setAttribute(
    "aria-label",
    dark ? "Ativar tema claro" : "Ativar tema escuro",
  );
  try {
    localStorage.setItem("ranking-theme-preference", dark ? "dark" : "light");
  } catch {}
}
function changed() {
  page = 1;
  donorLimit = 30;
  supplierLimit = 24;
  render();
}
document
  .querySelectorAll("[data-icon]")
  .forEach((e) => (e.innerHTML = icon(e.dataset.icon)));
hydrateURL();
renderView();
// A chave anterior também guardava o tema claro aplicado automaticamente.
// A nova preferência começa no escuro e respeita mudanças feitas pelo botão.
setTheme(document.documentElement.dataset.theme !== "light");
$("#theme").onclick = () =>
  setTheme(document.documentElement.dataset.theme !== "dark");
$("#abas").onclick = (e) => {
  const b = e.target.closest("[data-cargo]");
  if (!b) return;
  filtro.cargo = +b.dataset.cargo;
  changed();
};
$("#btn-novo").onclick = () => {
  filtro.partido = filtro.partido === "NOVO" ? "" : "NOVO";
  changed();
};
$("#partido").onchange = (e) => {
  filtro.partido = e.target.value;
  changed();
};
$("#busca").oninput = (e) => {
  filtro.busca = e.target.value;
  changed();
};
$("#ordem").onchange = (e) => {
  filtro.ordem = e.target.value;
  changed();
};
$("#clear-filters").onclick = () => {
  Object.assign(filtro, { cargo: 0, partido: "", busca: "" });
  changed();
};
$("#prev").onclick = () => {
  page--;
  renderRanking();
  $("#ranking-title").scrollIntoView({ block: "start" });
};
$("#next").onclick = () => {
  page++;
  renderRanking();
  $("#ranking-title").scrollIntoView({ block: "start" });
};
$("#donor-search").oninput = () => {
  donorLimit = 30;
  renderDonors(M.sum(current, M.net));
};
$("#supplier-search").oninput = () => {
  supplierLimit = 24;
  renderExpenses();
};
$("#more-donors").onclick = () => {
  donorLimit += 30;
  renderDonors(M.sum(current, M.net));
};
$("#more-suppliers").onclick = () => {
  supplierLimit += 24;
  renderExpenses();
};
$("#export").onclick = exportCSV;
$("#share").onclick = share;
$("#retry").onclick = () => carregar(true);
document.addEventListener("click", (e) => {
  const open = e.target.closest("[data-open]");
  if (open) {
    abrirModal(open.dataset.open);
    return;
  }
  const nav = e.target.closest("[data-view],[data-go]");
  if (nav) {
    view = nav.dataset.view || nav.dataset.go;
    renderView();
    updateURL();
    $(".filterbar").scrollIntoView({ block: "start", behavior: "instant" });
    return;
  }
  const dt = e.target.closest("[data-detail]");
  if (dt) {
    detailTab = dt.dataset.detail;
    renderDetail();
  }
});
$("#modal").addEventListener("keydown", (e) => {
  if (
    e.target.matches("[role=tab]") &&
    ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
  ) {
    e.preventDefault();
    const tabs = [...document.querySelectorAll("[data-detail]")];
    let i = tabs.indexOf(e.target);
    i =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? 2
          : (i + (e.key === "ArrowRight" ? 1 : 2)) % 3;
    detailTab = tabs[i].dataset.detail;
    renderDetail();
    tabs[i].focus();
  }
});
$("#modal").addEventListener("close", afterClose);
$("#modal").addEventListener("click", (e) => {
  if (e.target === $("#modal")) {
    const r = e.target.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      fecharModal();
  }
});
if (LOCAL) {
  $("#btn-refresh").hidden = false;
  $("#btn-refresh").onclick = async () => {
    const b = $("#btn-refresh");
    b.disabled = true;
    b.textContent = "Consultando o TSE…";
    try {
      const r = await fetch("api/atualizar", { method: "POST" });
      if (!r.ok) throw new Error();
      await carregar(true);
      toast("Dados atualizados.");
    } catch {
      toast("A coleta não concluiu. Os últimos dados foram preservados.");
    } finally {
      b.disabled = false;
      b.textContent = "Consultar o TSE agora";
    }
  };
}
window.addEventListener("popstate", () => {
  hydrateURL();
  changed();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) carregar();
});
carregar();
setInterval(() => {
  if (!document.hidden) carregar();
}, 60000);
setInterval(() => {
  if (dados) renderStatus();
}, 30000);

$("#back-filters").onclick = () =>
  $(".filterbar").scrollIntoView({ block: "start", behavior: "smooth" });
new IntersectionObserver(([entry]) => {
  $("#back-filters").hidden =
    entry.isIntersecting || entry.boundingClientRect.top > 0;
}).observe($(".filterbar"));
