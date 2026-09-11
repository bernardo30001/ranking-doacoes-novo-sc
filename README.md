# Ranking de Doações · Santa Catarina 2026

[Consultar o painel](https://bernardo30001.github.io/ranking-doacoes-novo-sc/)

Acompanha os candidatos a deputado federal e estadual de **todos os partidos em
Santa Catarina**, com o atalho **Só o NOVO**. A lista vem do TSE a cada coleta;
na revisão de 11/09/2026, eram 644 candidatos.

## Consultas disponíveis

- Ranking por arrecadação líquida, fundos públicos, FEFC, Fundo Partidário,
  outros recursos, despesas contratadas ou pagas.
- Filtros de partido, cargo e nome/número imediatamente acima da lista de
  candidatos; busca sem acentos.
- Doações uma a uma, fornecedores completos e categorias de despesa.
- Histórico diário e alterações de lançamentos entre coletas completas.
- Compartilhamento do recorte ou candidato por link, exportação CSV, temas
  claro e escuro e navegação adaptada ao celular e ao teclado.

## Como os números são interpretados

**Líquido = total recebido − receitas devolvidas.** O ranking, os indicadores e
as exportações descontam as devoluções. O histórico anterior não registrava
esse desconto: o gráfico identifica explicitamente os valores como brutos.
Variações líquidas só aparecem quando existe um ponto líquido anterior para
todos os candidatos do recorte; ausência de registro não equivale a zero.

**Quem transferiu e a fonte são classificações diferentes do mesmo valor.** Um
repasse de um candidato ou partido pode conservar a origem Fundo Partidário ou
Fundo Eleitoral informada pelo TSE. O painel preserva os rótulos de cada
lançamento. A soma entre campanhas pode contar o recebimento original e um
repasse posterior: não representa dinheiro único que entrou no estado.

**Contratado não significa pago.** Os fornecedores e categorias somam as despesas
contratadas; os pagamentos aparecem separadamente. As checagens são de
consistência aritmética, não de aprovação ou regularidade jurídica das contas.

Fonte: [DivulgaCandContas / TSE](https://divulgacandcontas.tse.jus.br/divulga/),
eleição `20322002026`, ano 2026, UF SC, cargos 6 e 7. Os valores refletem as
prestações disponibilizadas pelas campanhas e podem ser retificados.

## Atualização e publicação

O GitHub Actions está programado para executar de hora em hora, no minuto 17,
e também a cada alteração na `main`. Não depende de computador ligado.
O horário é uma programação, não garantia de execução pontual: depende da
fila do GitHub e da disponibilidade do TSE. A página consulta novas publicações
a cada minuto enquanto estiver visível.

1. Recupera a última publicação concluída e os caches de histórico e comparação.
2. Coleta em uma pasta temporária e confere os valores de todos os candidatos.
3. Só incorpora o novo conjunto se a coleta e a conferência passarem.
4. Se houver falha, conserva a última coleta completa, a data original e um
   aviso visível. A execução seguinte tenta novamente.
5. Publica os recursos com identificação pelo conteúdo, evitando mistura de
   arquivos de coletas diferentes e de versões antigas de CSS/JavaScript.
6. Salva os caches de comparação somente depois da publicação de dados novos.

`historico.json` e `estado.json`/`correcoes.json` usam caches separados para
preservar compatibilidade com a série já acumulada. O histórico também é
recuperado da publicação anterior caso o cache expire. Conserva-se até 45 dias;
o gráfico apresenta os últimos 14 registros disponíveis a partir da ampliação
para todos os partidos. O detector mantém os 300 eventos mais recentes e a
interface exibe até 60 por recorte. Se o estado de comparação expirar, a coleta
seguinte monta uma nova base, sem inventar alterações anteriores.

## Desenvolvimento e verificação

```sh
pip3 install -r requirements.txt
python3 servidor.py
```

O servidor abre em `http://localhost:8000`, restrito à própria máquina. Opções:
`--porta 8080`, `--minutos 30` e `--sem-navegador`. A coleta inicial pode demorar.
O botão de consulta ao TSE só existe no servidor local.

```sh
python3 atualizar.py                 # coleta e auditoria antes de substituir dados
python3 verificar.py                 # confere os arquivos existentes
python3 publicar.py                  # confere e monta _site para o GitHub Pages
python3 -m unittest discover -s tests
node --test tests/modelo.test.cjs
```

O coletor usa `curl_cffi` para compatibilidade com a conexão HTTPS do TSE.
Falhas de rede, arquivos incompletos, valores inválidos e desaparecimento de
prestações antes disponíveis interrompem a nova coleta, sem transformar falha
em receita zero. As 12 checagens financeiras precisam passar para publicação.
Os testes cobrem devoluções, agregação completa, homônimos, filtros, histórico,
retificações, falhas de rede e preservação da última versão.

O front-end não exige compilação: `index.html`, `estilo.css`, `modelo.js` e
`app.js`. `recuperar.py`, `atualizar.py` e `publicar.py` cuidam da recuperação,
atualização e montagem do site. Arquivos de dados publicados são gerados pelo
coletor; `estado.json` fica fora do site e do Git.

## Backup anterior à revisão

[Repositório privado do backup de 11/09/2026](https://github.com/bernardo30001/ranking-doacoes-novo-sc-backup-2026-09-11)

Contém o histórico Git anterior, os arquivos efetivamente publicados, os dados
e o histórico diário daquele momento, além de `RESTAURAR.md`. As automações
estão desativadas nesse repositório para manter o retrato preservado.
