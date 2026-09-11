# Ranking de Doações — NOVO / Santa Catarina · 2026

**No ar:** <https://bernardo30001.github.io/ranking-doacoes-novo-sc/>

Painel que acompanha quanto cada um dos **642 candidatos a Deputado Federal e
Deputado Estadual em Santa Catarina** arrecadou na eleição de 2026, e de onde o
dinheiro veio (Fundo Eleitoral, Fundo Partidário, doações privadas, vaquinhas).

Dá para filtrar por cargo, por partido e por nome. O botão **Só o NOVO** deixa
na tela apenas os candidatos do Partido NOVO.

O painel mostra, para cada candidato, **todas** as doações uma a uma (data, doador,
fonte e espécie), **para quem** a campanha pagou (fornecedor, CNPJ e categoria) e um
feed de **correções** — quando uma campanha muda o valor de uma doação que já havia
declarado ao TSE.

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
| `verificar.py` | audita se os valores de receita, fundos e despesa fecham entre si |
| `servidor.py` | serve o site e reexecuta o coletor de tempos em tempos |
| `index.html` / `estilo.css` / `app.js` | o painel |
| `dados.json` | o ranking: um registro por candidato, sem os lançamentos (gerado) |
| `agregados.json` | doadores, fornecedores e categorias por candidato (gerado) |
| `detalhe/<id>.json` | os lançamentos um a um, buscados só ao abrir um candidato (gerado) |
| `correcoes.json` | feed de redeclarações de prestação de contas (gerado) |
| `estado.json` | retrato dos lançamentos da rodada anterior, base da comparação (gerado, fora do git) |
| `historico.json` | um ponto por dia, usado para mostrar a variação (gerado) |

O painel carrega `dados.json` primeiro e busca o resto em segundo plano, para o
ranking aparecer sem esperar. Os lançamentos de um candidato só são baixados
quando alguém abre o card dele.

## Auditoria

`python3 verificar.py` confere, candidato a candidato, se os números do TSE fecham:

- receitas por natureza somam o total recebido;
- Fundo Eleitoral + Fundo Partidário + outros recursos somam os recursos financeiros;
- somando RONI e estimáveis, chega-se ao total líquido;
- a soma das doações itemizadas bate com o total líquido;
- a soma das despesas por categoria bate com o total de despesas contratadas;
- despesas pagas ≤ contratadas ≤ limite legal de gastos;
- fundos públicos ≤ total arrecadado, e nenhum valor negativo.

Sai com código 1 se alguma dessas contas não fechar. Roda também a cada coleta no
GitHub Actions, sem bloquear a publicação — se o TSE mandar algo estranho, o site
segue no ar e a divergência fica no log.

O relatório ainda lista quem **contratou mais despesa do que declarou ter
arrecadado**. Isso não é inconsistência: a despesa pode ser contratada a prazo.
Mas vale acompanhar.

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
- O ranking de doadores que o TSE exibe na tela do candidato traz só os **5
  maiores**. O painel não usa esse ranking: busca os lançamentos um a um, então a
  lista de doadores é completa. (Ex.: um candidato que aparecia com 5 doadores
  no TSE tem, de fato, 164.)
- **Bruto x líquido:** `totalRecebido` do TSE é bruto e inclui doação que foi
  devolvida. O painel mostra o líquido e, quando houve devolução, diz o valor.
- **RONI** é "recurso de origem não identificada"; **estimáveis** são bens e
  serviços doados em vez de dinheiro. Os dois entram na composição para que a
  barra sempre feche 100% do arrecadado.

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

## Detector de correções

A cada coleta o `coletar.py` compara os lançamentos de cada candidato com os da
rodada anterior (`estado.json`). Quando uma campanha **muda o valor de uma doação
que já havia declarado**, ou apaga uma, o evento entra em `correcoes.json` e
aparece no painel. Doação nova não entra: isso é o fluxo normal.

A comparação é por multiconjunto, e não por chave única, porque
`documento + data + doador + fonte` se repete (doações iguais no mesmo dia) e
parte dos lançamentos vem sem número de documento.

Foi assim que a Bia Borba (NOVO) saltou de R$ 814 mil para R$ 546 mil em 07/09:
um PIX de 04/09 foi redeclarado de R$ 280.000,00 para R$ 12.000,00.

## Fonte

Tribunal Superior Eleitoral — DivulgaCandContas, eleição `20322002026` (Geral Federal 2026).
