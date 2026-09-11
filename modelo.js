/* Regras compartilhadas pelo painel e pelos testes. Valores somados em centavos. */
(function (root) {
  "use strict";
  const cent = (v) => Math.round(Number(v || 0) * 100);
  const sum = (list, fn) => list.reduce((v, x) => v + cent(fn(x)), 0) / 100;
  const net = (c) =>
    (cent(c.total) - cent(c.devolvido ?? c.receitas?.devolvidas)) / 100;
  const publicFunds = (c) =>
    sum([c.origem.fundoEspecial, c.origem.fundoPartidario], (x) => x);
  const norm = (s) =>
    String(s ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .trim();
  const metric = (c, order) =>
    ({
      fundos: publicFunds(c),
      fefc: c.origem.fundoEspecial,
      fp: c.origem.fundoPartidario,
      outros: c.origem.outros,
      despesas: c.despesas.contratadas,
      pagas: c.despesas.pagas,
    })[order] ?? net(c);
  function filter(cands, f) {
    const q = norm(f.busca);
    return cands
      .filter(
        (c) =>
          (!f.cargo || c.cargo === Number(f.cargo)) &&
          (!f.partido || c.partido === f.partido) &&
          (!q || norm(`${c.nome} ${c.nomeCompleto} ${c.numero}`).includes(q)),
      )
      .sort(
        (a, b) =>
          (f.ordem === "nome"
            ? 0
            : cent(metric(b, f.ordem)) - cent(metric(a, f.ordem))) ||
          a.nome.localeCompare(b.nome, "pt-BR") ||
          a.id.localeCompare(b.id),
      );
  }
  function previousNet(c, p) {
    if (!p) return null;
    if (p.porCandidatoLiquido && Object.hasOwn(p.porCandidatoLiquido, c.id))
      return p.porCandidatoLiquido[c.id];
    // Retratos antigos não registravam devoluções: não comparar bruto com líquido.
    return null;
  }
  const delta = (c, p) => {
    const before = previousNet(c, p);
    return before === null ? null : (cent(net(c)) - cent(before)) / 100;
  };
  function recentRevenue(c, p) {
    const liquid = previousNet(c, p);
    if (liquid !== null && Number.isFinite(liquid)) {
      return { value: (cent(net(c)) - cent(liquid)) / 100, basis: "liquida" };
    }
    // O histórico antigo permite comparar bruto com bruto, nunca com líquido.
    const gross = p?.porCandidato?.[c.id];
    if (!Object.hasOwn(p?.porCandidato || {}, c.id) || !Number.isFinite(gross)) {
      return null;
    }
    return { value: (cent(c.total) - cent(gross)) / 100, basis: "bruta" };
  }
  function aggregate(cands, ag, field) {
    const map = new Map();
    for (const c of cands)
      for (const e of ag?.[c.id]?.[field] || []) {
        const key = String(e.cpfCnpj || norm(e.nome));
        if (!map.has(key))
          map.set(key, {
            key,
            nome: e.nome,
            doc: e.cpfCnpj,
            centavos: 0,
            qtd: 0,
            ids: new Set(),
            fcc: false,
          });
        const v = map.get(key);
        v.centavos += cent(e.valor);
        v.qtd += e.qtd || 0;
        v.ids.add(c.id);
        v.fcc ||= e.fcc;
      }
    return [...map.values()]
      .map((x) => ({ ...x, valor: x.centavos / 100 }))
      .sort(
        (a, b) =>
          b.centavos - a.centavos ||
          String(a.nome).localeCompare(String(b.nome), "pt-BR"),
      );
  }
  function safeURL(s) {
    try {
      const u = new URL(s);
      return ["https:", "http:"].includes(u.protocol) &&
        u.hostname.includes(".") &&
        !u.username &&
        !u.password
        ? u.href
        : null;
    } catch {
      return null;
    }
  }
  function csvCell(v) {
    let s = String(v ?? "");
    if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  }
  const api = {
    cent,
    sum,
    net,
    publicFunds,
    norm,
    metric,
    filter,
    previousNet,
    delta,
    recentRevenue,
    aggregate,
    safeURL,
    csvCell,
  };
  if (typeof module !== "undefined") module.exports = api;
  else root.Modelo = api;
})(typeof window !== "undefined" ? window : globalThis);
