const { test } = require("node:test");
const assert = require("node:assert/strict");
const M = require("../modelo.js");
const candidate = (id, total, returned = 0) => ({
  id,
  nome: "ÉRICO " + id,
  nomeCompleto: "ÉRICO VINICIUS",
  numero: 3000,
  cargo: 6,
  partido: "NOVO",
  total,
  devolvido: returned,
  origem: { fundoEspecial: 20, fundoPartidario: 10, outros: 15 },
  despesas: { contratadas: 12, pagas: 5 },
});
test("líquido ordena corretamente um candidato que devolveu recursos", () => {
  const a = candidate("a", 120, 40),
    b = candidate("b", 100);
  assert.equal(M.net(a), 80);
  assert.deepEqual(
    M.filter([a, b], { ordem: "total" }).map((c) => c.id),
    ["b", "a"],
  );
  assert.equal(M.sum([a, b], M.net), 180);
});
test("busca sem acentos combina cargo, partido e nome", () => {
  const a = candidate("a", 100),
    b = { ...candidate("b", 200), cargo: 7, partido: "PT" };
  assert.equal(
    M.filter([a, b], { busca: "erico vinicius", cargo: 6, partido: "NOVO" })
      .length,
    1,
  );
  assert.equal(M.filter([a, b], { busca: "não existe" }).length, 0);
});
test("histórico bruto nunca vira variação líquida; zero registrado é comparável", () => {
  const a = candidate("a", 100, 20);
  assert.equal(M.delta(a, { porCandidato: { a: 100 } }), null);
  assert.equal(M.delta(a, { porCandidatoLiquido: { a: 90 } }), -10);
  assert.equal(M.delta(a, { porCandidatoLiquido: { a: 0 } }), 80);
});
test("agregação não confunde candidatos homônimos nem arredonda por ocorrência", () => {
  const a = candidate("a", 0),
    b = candidate("b", 0);
  a.nome = b.nome = "PAULINHA";
  const ag = {
    a: {
      fornecedores: [{ cpfCnpj: "1", nome: "Fornecedor", valor: 0.1, qtd: 1 }],
    },
    b: {
      fornecedores: [{ cpfCnpj: "1", nome: "Fornecedor", valor: 0.2, qtd: 1 }],
    },
  };
  const result = M.aggregate([a, b], ag, "fornecedores")[0];
  assert.equal(result.valor, 0.3);
  assert.equal(result.ids.size, 2);
});
test("links inseguros e fórmulas de planilha são neutralizados", () => {
  assert.equal(M.safeURL("javascript:alert(1)"), null);
  assert.equal(M.safeURL("malformado"), null);
  assert.ok(M.safeURL("https://tse.jus.br"));
  assert.equal(M.safeURL("https://https//x.com/exemplo"), null);
  assert.equal(M.safeURL("https://user:pass@tse.jus.br"), null);
  assert.equal(M.csvCell("=1+2"), '"\'=1+2"');
  assert.equal(M.csvCell('A "B"'), '"A ""B"""');
});
test("coluna de valor corresponde à ordenação selecionada", () => {
  const a = candidate("a", 100);
  assert.equal(M.metric(a, "fundos"), 30);
  assert.equal(M.metric(a, "despesas"), 12);
  assert.equal(M.metric(a, "pagas"), 5);
});

test("variação recente compara bruto com bruto ao recuperar o histórico antigo", () => {
  const c = candidate("a", 150, 60);
  assert.deepEqual(M.recentRevenue(c, {porCandidato: {a: 100}}), {value: 50, basis: "bruta"});
  assert.deepEqual(M.recentRevenue(c, {porCandidato: {a: 100}, porCandidatoLiquido: {a: 100}}), {value: -10, basis: "liquida"});
});
test("variação recente distingue zero registrado de candidato sem histórico", () => {
  const c = candidate("a", 100);
  assert.deepEqual(M.recentRevenue(c, {porCandidato: {a: 0}}), {value: 100, basis: "bruta"});
  assert.equal(M.recentRevenue(c, {porCandidato: {b: 100}}), null);
  assert.equal(M.recentRevenue(c, {porCandidato: {a: null}}), null);
  assert.equal(M.recentRevenue(c, undefined), null);
});
test("variação recente conserva centavos e identifica ausência de mudança", () => {
  const c = candidate("a", 100.02);
  assert.deepEqual(M.recentRevenue(c, {porCandidato: {a: 100}}), {value: .02, basis: "bruta"});
  assert.deepEqual(M.recentRevenue(c, {porCandidatoLiquido: {a: 100.02}}), {value: 0, basis: "liquida"});
});
