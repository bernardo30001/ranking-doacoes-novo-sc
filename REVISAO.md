# Revisão de 11/09/2026

Escopo: cálculos, integridade da coleta, atualização automática, histórico,
navegação, celular, compartilhamento e legibilidade. Referência anterior:
commit `d7d6dca9ffbe8839c367d29bee299e99361be7d6`, publicação do run `34560193530`.

## Problemas corrigidos

| Achado | Impacto e correção |
|---|---|
| Parte do ranking ainda usava receita bruta | Bruno Souza aparecia com R$ 381.822,50 apesar da devolução de R$ 15.911,25. Ranking, resumo e CSV agora usam R$ 365.911,25 líquidos. |
| Agregação guardava apenas 20 fornecedores por candidato | R$ 2.298.754,66 de despesas ficavam fora da soma dos fornecedores. Todos os fornecedores passam a compor a lista e a conferência. |
| Campanhas homônimas eram contadas pelo nome | Contagem de candidatos por fornecedor agora usa o identificador do TSE. |
| Falhas de consultas podiam se tornar listas vazias | Falha de transporte interrompe a nova coleta. Atualização em pasta temporária preserva dados, histórico e estado anterior. |
| Publicação ignorava falhas da auditoria | As 12 checagens precisam passar. Se a nova coleta não concluir, a última publicação completa permanece com seu horário e aviso. |
| Detalhes podiam permanecer em cache após nova coleta | Recursos versionados pelo conteúdo; troca conjunta dos arquivos e descarte do detalhe antigo. Respostas atrasadas não trocam o candidato aberto. |
| Variação misturava base bruta com valor líquido | Comparação líquida exige registro líquido anterior; zeros registrados são distintos de ausência de dados. |
| Histórico dependia exclusivamente de cache | Recuperação adicional da publicação anterior e caches separados, mantendo os 16 dias existentes na revisão. |
| Links externos malformados | Links sem domínio válido, credenciais ou protocolo permitido são omitidos. |
| Falha no detalhe podia parecer ausência de doações | Exibe erro explícito de carregamento. |

Na publicação de referência, a receita líquida estadual é **R$ 124.286.522,75**
e as despesas contratadas são **R$ 21.589.924,38**. Com a agregação completa,
Facebook Serviços Online do Brasil totaliza **R$ 1.680.437,67**, em **121
candidatos distintos**. São valores dessa coleta; atualizações posteriores
podem mudar o ranking.

## Design e uso

Identidade visual independente do TSE; navegação por candidatos, doadores,
despesas, alterações e metodologia; indicadores com valores exatos; composição
por fonte; gráfico com tabela diária; filtros compartilhados entre as áreas;
atalho do NOVO; paginação de 25 candidatos; tema escuro opcional; detalhes em
janela acessível por teclado; CSV e links que conservam filtros e candidato.

A seção de metodologia explica origem versus doador, bruto versus líquido,
contratado versus pago e a possibilidade de transferências entre campanhas
aparecerem em mais de uma receita agregada. Nenhum desses cálculos, sozinho,
comprova regularidade ou irregularidade de contas.

## Verificação

- 15 testes automatizados de cálculos, filtros, histórico, correções e recuperação.
- 12 checagens financeiras aprovadas para os 644 candidatos da referência.
- Recuperação integral testada com o artefato real do site anterior.
- Navegação conferida em navegador, incluindo celular, NOVO + cargo, busca sem
  acentos, devolução de Bruno Souza e fornecedores completos.

## Preservação

Backup privado: https://github.com/bernardo30001/ranking-doacoes-novo-sc-backup-2026-09-11

Commit do backup: `3b516f8a7676b1312536a4ac53e84ecb065491cb`. Inclui código,
histórico Git, publicação anterior e instruções de restauração. Actions
está desativado no backup.
