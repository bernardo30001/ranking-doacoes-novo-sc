# Ranking de Doações — NOVO / Santa Catarina · 2026

**No ar:** <https://bernardo30001.github.io/ranking-doacoes-novo-sc/>

Painel que acompanha quanto cada candidato do **Partido NOVO em Santa Catarina** a
**Deputado Federal** e **Deputado Estadual** arrecadou na eleição de 2026, e de onde
o dinheiro veio (Fundo Eleitoral, Fundo Partidário, doações privadas, vaquinhas).

Os dados vêm direto do [DivulgaCandContas do TSE](https://divulgacandcontas.tse.jus.br/divulga/)
e são recoletados sozinhos enquanto o servidor estiver rodando.

## Como rodar

```bash
pip3 install -r requirements.txt
python3 servidor.py
```

O painel abre em <http://localhost:8000> e se atualiza a cada 30 minutos.

| opção | o que faz |
|---|---|
| `--minutos 10` | muda o intervalo entre coletas |
| `--porta 8080` | muda a porta |
| `--sem-navegador` | não abre o navegador sozinho |

O botão **Atualizar agora** no cabeçalho força uma coleta na hora.

Para só baixar os dados, sem servidor:

```bash
python3 coletar.py
```

## Arquivos

| arquivo | o que é |
|---|---|
| `coletar.py` | busca os candidatos e as prestações de contas no TSE → `dados.json` |
| `servidor.py` | serve o site e reexecuta o coletor de tempos em tempos |
| `index.html` / `estilo.css` / `app.js` | o painel |
| `dados.json` | último retrato completo (gerado) |
| `historico.json` | um ponto por dia, usado para mostrar a variação (gerado) |

## Sobre os dados

- **Fundo Eleitoral (FEFC)** e **Fundo Partidário** são dinheiro público. O partido
  recebe e repassa aos candidatos.
- **Outros recursos** é tudo que não saiu desses dois fundos: doações de pessoas
  físicas, vaquinhas, recursos próprios e repasses do partido feitos com dinheiro
  próprio dele.
- Por isso um repasse do "Direção Nacional – NOVO" pode aparecer dividido entre fundo
  e outros recursos: o TSE rastreia a origem original de cada real.
- O TSE atualiza os dados de candidatura a cada 60 minutos. As prestações de contas
  mudam quando cada campanha entrega um novo relatório — o painel reflete a última
  entrega disponível, então "tempo real" aqui significa "o mais recente que o TSE
  publicou", não valores minuto a minuto.
- Valores são **parciais** até a prestação de contas final.

## Detalhe técnico

O TSE fica atrás de um WAF (Akamai) que bloqueia clientes HTTP comuns pelo
*fingerprint* de TLS — `curl` e `requests` levam 403. Por isso o coletor usa
`curl_cffi`, que imita o handshake do Chrome.

## Como o site publicado se mantém atualizado

`.github/workflows/atualizar.yml` roda de hora em hora no GitHub Actions: coleta do
TSE, monta a pasta do site e publica no GitHub Pages. Não é preciso deixar nada
ligado aqui.

O `historico.json` (usado para a variação diária) sobrevive entre execuções via
cache do Actions.

Para forçar uma atualização fora da hora:

```bash
gh workflow run "Atualizar dados e publicar"
```

No site publicado o botão "Atualizar agora" não aparece — não há coletor do outro
lado. Ele só existe quando você roda `servidor.py` na sua máquina.

## Fonte

Tribunal Superior Eleitoral — DivulgaCandContas, eleição `20322002026` (Geral Federal 2026).
