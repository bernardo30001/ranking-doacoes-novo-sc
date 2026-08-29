'use strict';

const FONTES = [
  { chave: 'fundoEspecial',   rotulo: 'Fundo Eleitoral (FEFC)',  cor: 'var(--fefc)' },
  { chave: 'fundoPartidario', rotulo: 'Fundo Partidário',        cor: 'var(--fundo)' },
  { chave: 'outros',          rotulo: 'Outros recursos',         cor: 'var(--priv)' },
  { chave: 'roni',            rotulo: 'Origem não identificada', cor: 'var(--roni)' },
  { chave: 'estimavel',       rotulo: 'Estimáveis (não em R$)',  cor: 'var(--estim)' },
];

const RECEITAS = [
  ['pessoaFisica', 'Pessoas físicas'],
  ['pessoaJuridica', 'Pessoas jurídicas'],
  ['partidos', 'Partidos'],
  ['outrosCandidatos', 'Outros candidatos'],
  ['proprios', 'Recursos próprios'],
  ['financiamentoColetivo', 'Financiamento coletivo'],
  ['internet', 'Doação pela internet'],
  ['roni', 'RONIs'],
  ['comercializacao', 'Comercialização de bens'],
  ['aplicacoes', 'Aplicações financeiras'],
  ['bens', 'Bens móveis/imóveis'],
];

let dados = null;
let historico = [];

/* So o servidor local tem o coletor atras de /api/atualizar. Publicado no
   GitHub Pages a atualizacao vem do cron, entao o botao nao faz sentido. */
const TEM_COLETOR = ['localhost', '127.0.0.1', ''].includes(location.hostname);
const DESTAQUE = 'NOVO';
const filtro = { cargo: 0, partido: '', busca: '', ordem: 'total' };

const $ = (s) => document.querySelector(s);
const brl = (v) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2 });
const brlCurto = (v) => {
  if (v >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' mi';
  if (v >= 1000) return 'R$ ' + (v / 1000).toLocaleString('pt-BR', { maximumFractionDigits: v >= 100000 ? 0 : 1 }) + ' mil';
  return brl(v);
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function docFormatado(d) {
  if (!d) return '';
  const n = d.replace(/\D/g, '');
  if (n.length === 11) return 'CPF ' + n.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
  if (n.length === 14) return 'CNPJ ' + n.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
  return d;
}

function fundosDe(c) { return c.origem.fundoEspecial + c.origem.fundoPartidario; }
function somaDoadores(c) { return c.doadores.reduce((s, d) => s + d.valor, 0); }

/* Ultimo ponto do historico anterior ao dia de hoje, para calcular a variacao. */
function pontoAnterior() {
  if (historico.length < 2) return null;
  const hoje = dados.atualizadoEm.slice(0, 10);
  for (let i = historico.length - 1; i >= 0; i--) {
    if (historico[i].data < hoje) return historico[i];
  }
  return null;
}

/* null quando o candidato nao existia no retrato anterior: ai nao ha variacao
   a mostrar, e tratar a ausencia como zero inventaria uma alta que nao houve. */
function variacaoDe(c) {
  const p = pontoAnterior();
  if (!p || !(c.id in p.porCandidato)) return null;
  return c.total - p.porCandidato[c.id];
}

function dataCurta(iso) {
  const [a, m, d] = iso.split('-');
  return `${d}/${m}`;
}

/* ---------------- carregamento ---------------- */

async function carregar(silencioso) {
  try {
    const r = await fetch('dados.json?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    dados = await r.json();
    montarPartidos();
    try {
      const h = await fetch('historico.json?t=' + Date.now(), { cache: 'no-store' });
      historico = h.ok ? await h.json() : [];
    } catch { historico = []; }
    render();
  } catch (e) {
    if (!silencioso) $('#status').textContent = 'não consegui carregar dados.json — rode o coletor primeiro';
  }
}

async function forcarAtualizacao() {
  const btn = $('#btn-refresh');
  btn.disabled = true;
  btn.textContent = 'Consultando TSE…';
  try {
    const r = await fetch('api/atualizar', { method: 'POST' });
    // Sem servidor (site estatico) nao ha coletor para chamar: some com o botao.
    if (r.status === 404 || r.status === 405 || r.status === 501) {
      btn.remove();
      return;
    }
    if (!r.ok) throw new Error('HTTP ' + r.status);
    await carregar();
    btn.textContent = 'Atualizar agora';
  } catch {
    btn.textContent = 'Falhou — tentar de novo';
  } finally {
    btn.disabled = false;
  }
}

/* ---------------- render ---------------- */

/* O select de partidos vem dos dados, nao de uma lista fixa no codigo. */
function montarPartidos() {
  const sel = $('#partido');
  if (sel.options.length > 1) return;
  const contagem = {};
  dados.candidatos.forEach((c) => contagem[c.partido] = (contagem[c.partido] || 0) + 1);
  sel.insertAdjacentHTML('beforeend', (dados.partidos || []).map((p) =>
    `<option value="${esc(p)}">${esc(p)} (${contagem[p] || 0})</option>`).join(''));
  sel.value = filtro.partido;
}

function render() {
  if (!dados) return;
  renderStatus();
  aplicarFiltro();
}

/* Tudo que a tela mostra deriva do recorte ativo, entao um lugar so o recalcula. */
function aplicarFiltro() {
  const lista = candidatosFiltrados();
  renderSelo();
  renderResumo(lista);
  renderComposicaoGlobal(lista);
  renderLista(lista);
  renderDoadores(lista);
}

function renderSelo() {
  const partes = [filtro.partido || 'Todos os partidos'];
  if (filtro.cargo) partes.push(filtro.cargo === 6 ? 'Dep. Federal' : 'Dep. Estadual');
  partes.push('Santa Catarina · 2026');
  $('#selo').textContent = partes.join(' · ');
  $('#btn-novo').classList.toggle('on', filtro.partido === DESTAQUE);
}

function renderStatus() {
  const d = new Date(dados.atualizadoEm);
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  const quando = min < 1 ? 'agora mesmo' : min < 60 ? `há ${min} min` : `há ${Math.floor(min / 60)}h`;
  const cadencia = TEM_COLETOR ? '' : ' · atualiza sozinho de hora em hora';
  $('#status').textContent =
    `Atualizado ${quando} · ${d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}${cadencia}`;
  $('#rodape-atualizacao').textContent = ` Última coleta: ${d.toLocaleString('pt-BR')}.`;
}

function renderResumo(lista) {
  const soma = (f) => lista.reduce((s, c) => s + f(c), 0);
  const total = soma((c) => c.total) || 0;
  const pct = (v) => `${(v / (total || 1) * 100).toFixed(1)}% do total`;
  const comReceita = lista.filter((c) => c.total > 0).length;

  const fundos = soma((c) => c.origem.fundoEspecial + c.origem.fundoPartidario);
  const doPartido = soma((c) => c.receitas.partidos);
  const pf = soma((c) => c.receitas.pessoaFisica);
  const gastos = soma((c) => c.despesas.contratadas);

  // A variacao so faz sentido sobre o mesmo recorte que esta na tela, e so
  // entre candidatos que ja apareciam no retrato anterior.
  const p = pontoAnterior();
  const comparaveis = p ? lista.filter((c) => c.id in p.porCandidato) : [];
  // Se o retrato anterior cobre pouco do que esta na tela, a variacao seria de
  // um recorte diferente do total exibido — melhor nao mostrar do que enganar.
  const comparavel = comparaveis.length >= Math.max(1, lista.filter((c) => c.total > 0).length * 0.9);
  const delta = comparaveis.reduce((s, c) => s + c.total - p.porCandidato[c.id], 0);
  const notaTotal = comparavel
    ? `${delta >= 0 ? '+' : ''}${brl(delta)} desde ${dataCurta(p.data)} · ${comReceita}/${lista.length} com receita`
    : `${comReceita} de ${lista.length} candidatos com receita`;

  const cards = [
    { rot: 'Total arrecadado', val: brl(total), nota: notaTotal, destaque: true },
    { rot: 'Veio dos fundos públicos', val: brl(fundos), nota: `${pct(fundos)} · fundo eleitoral + partidário` },
    { rot: 'Repassado por partidos', val: brl(doPartido), nota: pct(doPartido) },
    { rot: 'Doado por pessoas físicas', val: brl(pf), nota: pct(pf) },
    { rot: 'Já gastaram', val: brl(gastos), nota: 'despesas contratadas declaradas' },
  ];
  $('#resumo').innerHTML = cards.map((c) => `
    <div class="card${c.destaque ? ' destaque' : ''}">
      <div class="rot">${c.rot}</div>
      <div class="val">${c.val}</div>
      <div class="nota">${c.nota}</div>
    </div>`).join('');
}

function renderComposicaoGlobal(lista) {
  const soma = {};
  FONTES.forEach((f) => soma[f.chave] = lista.reduce((s, c) => s + c.origem[f.chave], 0));
  const total = Object.values(soma).reduce((a, b) => a + b, 0) || 1;

  $('#barra-global').innerHTML = FONTES.map((f) =>
    `<div style="width:${soma[f.chave] / total * 100}%;background:${f.cor}" title="${f.rotulo}"></div>`).join('');

  // Baldes zerados so poluiriam a legenda (RONI e estimaveis quase sempre sao 0).
  $('#legenda-global').innerHTML = FONTES.filter((f) => soma[f.chave] > 0).map((f) =>
    `<span><i style="background:${f.cor}"></i>${f.rotulo} <b>${brl(soma[f.chave])}</b> · ${(soma[f.chave] / total * 100).toFixed(1)}%</span>`).join('');
}

function candidatosFiltrados() {
  const busca = filtro.busca.trim().toLowerCase();
  let l = dados.candidatos.filter((c) =>
    (!filtro.cargo || c.cargo === filtro.cargo) &&
    (!filtro.partido || c.partido === filtro.partido) &&
    (!busca || c.nome.toLowerCase().includes(busca) || (c.nomeCompleto || '').toLowerCase().includes(busca) || String(c.numero).includes(busca))
  );
  const ordens = {
    total: (a, b) => b.total - a.total,
    fundos: (a, b) => fundosDe(b) - fundosDe(a),
    privado: (a, b) => b.origem.outros - a.origem.outros,
    despesas: (a, b) => b.despesas.contratadas - a.despesas.contratadas,
    nome: (a, b) => a.nome.localeCompare(b.nome, 'pt-BR'),
  };
  return l.sort(ordens[filtro.ordem]);
}

function renderLista(lista) {
  const maior = Math.max(...lista.map((c) => c.total), 1);

  $('#lista').innerHTML = lista.map((c, i) => {
    const iniciais = c.nome.split(/\s+/).slice(0, 2).map((p) => p[0]).join('');
    const foto = c.foto
      ? `<img class="foto" src="${esc(c.foto)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'foto vazia',textContent:'${esc(iniciais)}'}))">`
      : `<div class="foto vazia">${esc(iniciais)}</div>`;

    const larguraTotal = c.total / maior * 100;
    const segmentos = c.total
      ? FONTES.map((f) => `<div style="width:${c.origem[f.chave] / c.total * 100}%;background:${f.cor}"></div>`).join('')
      : '';
    const fp = fundosDe(c);
    const rotBarra = c.total
      ? `${(fp / c.total * 100).toFixed(0)}% fundos públicos · ${(c.origem.outros / c.total * 100).toFixed(0)}% outros`
      : 'sem receita declarada';

    return `
    <div class="linha${c.total ? '' : ' zero'}" data-id="${c.id}">
      <div class="pos">${i + 1}</div>
      ${foto}
      <div class="quem">
        <div class="nome">${esc(c.nome)}</div>
        <div class="meta"><em>${c.numero}</em> · <span class="sigla${c.partido === DESTAQUE ? ' destaque' : ''}">${esc(c.partido || '—')}</span> · ${esc(c.cargoNome)} · ${esc(c.situacao || '')}</div>
      </div>
      <div class="barra-cell">
        <div class="mini" style="width:${Math.max(larguraTotal, 3)}%">${segmentos}</div>
        <div class="mini-rot">${rotBarra}</div>
      </div>
      <div class="dinheiro">
        <div class="v">${c.total ? brl(c.total) : 'R$ 0,00'}</div>
        <div class="n">${c.qtdDoacoes} ${c.qtdDoacoes === 1 ? 'doação' : 'doações'}${
          variacaoDe(c) > 0 ? ` · <span class="alta">+${brlCurto(variacaoDe(c))}</span>` : ''}</div>
      </div>
    </div>`;
  }).join('') || '<p class="vazio">Nenhum candidato encontrado.</p>';

  $('#lista').querySelectorAll('.linha').forEach((el) =>
    el.addEventListener('click', () => abrirModal(el.dataset.id)));
}

function renderDoadores(lista) {
  const mapa = new Map();
  lista.forEach((c) => c.doadores.forEach((d) => {
    const k = d.cpfCnpj || d.nome;
    const e = mapa.get(k) || { nome: d.nome, doc: d.cpfCnpj, valor: 0, qtd: 0, candidatos: new Set(), fcc: d.fcc };
    e.valor += d.valor;
    e.qtd += d.qtd;
    e.candidatos.add(c.nome);
    mapa.set(k, e);
  }));

  const top = [...mapa.values()].sort((a, b) => b.valor - a.valor).slice(0, 30);
  $('#doadores').innerHTML = top.map((d, i) => `
    <div class="doador">
      <span class="idx">${i + 1}</span>
      <div class="info">
        <b>${esc(d.nome)}${d.fcc ? '<span class="etiqueta">vaquinha</span>' : ''}</b>
        <span>${docFormatado(d.doc)} · ${d.candidatos.size} ${d.candidatos.size === 1 ? 'candidato' : 'candidatos'}</span>
      </div>
      <span class="v">${brlCurto(d.valor)}</span>
    </div>`).join('') || '<p class="vazio">Nenhuma doação registrada ainda.</p>';
}

/* ---------------- modal ---------------- */

function abrirModal(id) {
  const c = dados.candidatos.find((x) => x.id === id);
  if (!c) return;

  const iniciais = c.nome.split(/\s+/).slice(0, 2).map((p) => p[0]).join('');
  const foto = c.foto
    ? `<img class="foto" src="${esc(c.foto)}" alt="">`
    : `<div class="foto vazia">${esc(iniciais)}</div>`;

  const receitas = RECEITAS.map(([k, r]) => [r, c.receitas[k]]).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const usoLimite = c.limiteGasto ? (c.despesas.contratadas / c.limiteGasto * 100) : 0;

  const linhaTabela = (nome, sub, valor, pct) => `
    <tr><td>${esc(nome)}${sub ? `<div class="doc">${sub}</div>` : ''}</td>
    <td>${brl(valor)}${pct != null ? `<div class="doc">${pct.toFixed(1)}%</div>` : ''}</td></tr>`;

  $('#modal-conteudo').innerHTML = `
    <div class="modal-topo">
      ${foto}
      <div>
        <h3>${esc(c.nome)}</h3>
        <p>${esc(c.nomeCompleto || '')}</p>
        <p>${c.numero} · ${esc(c.partido || '')} · ${esc(c.cargoNome)} · ${esc(c.situacao || '')} · ${esc(c.ocupacao || '')}</p>
      </div>
      <button class="fechar" aria-label="Fechar">&times;</button>
    </div>
    <div class="modal-corpo">
      <div class="grade">
        <div class="mini-card"><div class="rot">Arrecadado</div><div class="val" style="color:var(--novo)">${brl(c.total)}</div></div>
        <div class="mini-card"><div class="rot">Fundo Eleitoral</div><div class="val" style="color:var(--fefc)">${brl(c.origem.fundoEspecial)}</div></div>
        <div class="mini-card"><div class="rot">Fundo Partidário</div><div class="val" style="color:var(--fundo)">${brl(c.origem.fundoPartidario)}</div></div>
        <div class="mini-card"><div class="rot">Outros recursos</div><div class="val" style="color:var(--priv)">${brl(c.origem.outros)}</div></div>
      </div>

      ${c.total ? `<div class="barra">${FONTES.map((f) =>
        `<div style="width:${c.origem[f.chave] / c.total * 100}%;background:${f.cor}"></div>`).join('')}</div>` : ''}

      <div class="bloco">
        <h4>Principais doadores${c.doadores.length ? ` (${c.doadores.length})` : ''}</h4>
        ${c.doadores.length
          ? `<table class="tab">${c.doadores.map((d) =>
              linhaTabela(d.nome + (d.fcc ? ' 🐖' : ''), docFormatado(d.cpfCnpj) + ` · ${d.qtd}×`, d.valor, c.total ? d.valor / c.total * 100 : 0)).join('')}</table>
             ${somaDoadores(c) < c.total - 0.05
               ? `<p class="ressalva">O TSE publica só os 5 maiores doadores. Faltam ${brl(c.total - somaDoadores(c))} de doadores menores, não detalhados.</p>`
               : ''}`
          : '<p class="vazio">Nenhuma doação declarada até agora.</p>'}
      </div>

      ${receitas.length ? `<div class="bloco">
        <h4>Natureza das receitas</h4>
        <table class="tab">${receitas.map(([r, v]) => linhaTabela(r, '', v, c.total ? v / c.total * 100 : 0)).join('')}</table>
      </div>` : ''}

      ${c.despesas.contratadas > c.total + 0.05
        ? `<p class="ressalva alerta">Contratou ${brl(c.despesas.contratadas)} em despesas, mais do que os ${brl(c.total)} que declarou ter arrecadado. É permitido — a despesa pode ser contratada a prazo — mas a receita ainda não apareceu na prestação de contas.</p>`
        : ''}

      <div class="bloco">
        <h4>Despesas</h4>
        <table class="tab">
          ${linhaTabela('Contratadas', '', c.despesas.contratadas)}
          ${linhaTabela('Pagas', '', c.despesas.pagas)}
          ${c.limiteGasto ? linhaTabela('Limite legal de gastos', `usou ${usoLimite.toFixed(1)}% do limite`, c.limiteGasto) : ''}
        </table>
      </div>

      ${c.fornecedores.length ? `<div class="bloco">
        <h4>Fornecedores</h4>
        <table class="tab">${c.fornecedores.map((f) => linhaTabela(f.nome, docFormatado(f.cpfCnpj), f.valor)).join('')}</table>
      </div>` : ''}

      ${c.entregas.length ? `<div class="bloco">
        <h4>Entregas de prestação de contas (${c.entregas.length})</h4>
        <table class="tab">${c.entregas.slice(0, 8).map((e) =>
          `<tr><td>${esc(e.data)}${e.retificadora ? '<div class="doc">retificadora</div>' : ''}</td><td style="font-weight:400;color:var(--txt-2)">${esc(e.tipo)}</td></tr>`).join('')}</table>
      </div>` : ''}

      <div class="links">
        <a href="${esc(c.urlTse)}" target="_blank" rel="noopener">Ver no TSE ↗</a>
        ${(c.sites || []).map((s) => `<a href="${esc(s)}" target="_blank" rel="noopener nofollow">${esc(new URL(s).hostname.replace('www.', ''))} ↗</a>`).join('')}
      </div>
    </div>`;

  $('#modal').classList.add('on');
  document.body.style.overflow = 'hidden';
  $('#modal-conteudo .fechar').addEventListener('click', fecharModal);
}

function fecharModal() {
  $('#modal').classList.remove('on');
  document.body.style.overflow = '';
}

/* ---------------- eventos ---------------- */

$('#abas').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  $('#abas').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
  filtro.cargo = Number(b.dataset.cargo);
  aplicarFiltro();
});

$('#btn-novo').addEventListener('click', () => {
  filtro.partido = filtro.partido === DESTAQUE ? '' : DESTAQUE;
  $('#partido').value = filtro.partido;
  aplicarFiltro();
});

$('#partido').addEventListener('change', (e) => { filtro.partido = e.target.value; aplicarFiltro(); });
$('#busca').addEventListener('input', (e) => { filtro.busca = e.target.value; aplicarFiltro(); });
$('#ordem').addEventListener('change', (e) => { filtro.ordem = e.target.value; aplicarFiltro(); });
$('#btn-refresh').addEventListener('click', forcarAtualizacao);
$('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') fecharModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharModal(); });

if (!TEM_COLETOR) $('#btn-refresh').remove();

carregar();
setInterval(() => carregar(true), 60000);
setInterval(renderStatus, 30000);
