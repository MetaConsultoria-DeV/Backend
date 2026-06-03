# Runbook do Agent de BACKEND — Ingestão Pipefy de Vendas (Comercial)

> **Para o agent:** você roda dentro da pasta do backend FastAPI do Davi. Sua missão:
> (1) estruturar tudo que ainda **não existe** pra ingestão do **Pipefy de Vendas**
> (pipe "Sales Pipeline"), (2) criar **migrations** só se forem necessárias, (3) no
> final, escrever o handoff `HANDOFF_FLUXO_VENDAS.md` — o contrato que o **outro agent
> (o do fluxo n8n)** vai ler. Siga as fases na ordem. **Pare nos checkpoints 🚦 e
> espere a resposta do Davi.** Sempre responda em português.
>
> **Ordem do projeto:** este agent roda PRIMEIRO. O agent do fluxo n8n roda DEPOIS,
> e depende do seu `HANDOFF_FLUXO_VENDAS.md`. Não é você quem cria o JSON do n8n.
>
> **Existe um precedente funcionando:** a ingestão do **Pipefy Financeiro** já está
> pronta em `ingestion/pipefy/` (client, transform, matching, load, sync, router) e o
> endpoint `POST /internal/sync/pipefy-financeiro`. **Espelhe a arquitetura dela** — não
> reinvente padrão. Você está fazendo a versão Comercial do mesmo desenho.

---

## ⛔ Regra de escopo (decisão do Davi — não reabrir)

**O alvo é exatamente o que o schema já comporta.** Preencha **somente as tabelas
comerciais que já existem** e, dentro delas, **somente as colunas que já existem**.

- **Campo do Pipefy que não tem coluna no schema → ignore.** Não traga "todos os dados"
  do pipe; traga só o que tem casa no banco.
- **Não crie tabela nova. Não crie coluna nova** (a única migration *talvez* aceitável é
  uma de idempotência/índice — ver Fase 2 — e mesmo assim só se faltar).
- Se um dado do Pipefy parecer útil mas não tiver coluna, **liste no checkpoint** e siga
  sem ele; quem decide ampliar schema é o Davi, fora deste agent.

---

## Arquitetura (n8n fino)

Toda a lógica pesada é sua, em Python testável: chamar o GraphQL do Pipefy, transformar,
resolver dimensões/etiquetas, calcular duração de fase, fazer matching e upsert. O n8n
(outro agent) só vai agendar e disparar um endpoint seu. Logo, **o token do Pipefy e o
MySQL vivem aqui no backend**, não no n8n.

```
[Schedule] → [HTTP POST /internal/sync/pipefy-comercial] → [IF erro] → [Outlook: alerta]
```

---

## Tabelas-alvo (as 5 do comercial, já existem VAZIAS no schema)

| Tabela | Papel | Âncora de idempotência |
|---|---|---|
| `dim_lead_origem` | taxonomia de origem do lead (raw→canonical) | `uk_dim_lead_origem_raw(source_field, raw_value)` |
| `dim_motivo_perda` | taxonomia de motivo de perda (raw→canonical) | `uk_dim_motivo_perda_raw(source_field, raw_value)` |
| `leads` | contato comercial (pode gerar N oportunidades) | `uk_lead_external(external_source, external_id)` |
| `oportunidade` | **o card** (estado atual) | `uk_oportunidade_external(external_source, external_id)` |
| `oportunidade_phase_history` | histórico de fase (append-only) | `uk_oport_phase_event(external_source, external_event_id)` |

`external_source` do comercial = **`pipefy_comercial`** (já é o DEFAULT em `oportunidade`).
Para o histórico de fase, use um `external_source` próprio do evento (ex.:
`pipefy_comercial_phase`) e um `external_event_id` estável por movimentação — assim o
re-sync não duplica eventos.

---

## Fase 0 — Reconhecimento (antes de escrever qualquer linha)

Leia, nesta ordem:
1. `schema0106.sql` — as **5 tabelas-alvo** acima e suas `UNIQUE KEY` de idempotência.
   Confirme **coluna por coluna** o que existe (é o teto do que você pode gravar).
2. `ingestion/pipefy/` (financeiro) — copie a estrutura: `client.py` (GraphQL paginado),
   `transform.py`, `matching.py`, `load.py`, `sync.py`, `router.py`. Veja como o
   `field_map.py` congela `field.id`, como o pool MySQL é usado (`database.py`:
   `execute_query`, `execute_insert`, `transaction`) e como o token sobe do `.env`.
3. Como rodam os testes (`tests/`) e o padrão de rotas em `main.py`.

> 🚦 **Checkpoint 0.** Devolva ao Davi: o mapa **coluna→origem provável** das 5 tabelas,
> o que **já existe** (módulo financeiro reaproveitável) vs. o que vai **criar**
> (módulo comercial), e qualquer campo do Pipefy que você prevê **descartar por não ter
> coluna**. Espere o "ok".

---

## Fase 1 — Credenciais que o BACKEND possui

Conduza o Davi. **Não peça segredo colado no chat** — tudo vai pro `.env` (e, em produção,
pra aba **Ambiente** do EasyPanel, porque o `.dockerignore` exclui o `.env`).

| Credencial | Var no `.env` | Observação |
|---|---|---|
| Pipefy Service Account token | `PIPEFY_TOKEN` | **Provavelmente o mesmo do financeiro** — mesma conta Pipefy, outro pipe. Confirme que o Service Account enxerga o pipe de Vendas. PAT continua deprecado. |
| Conexão MySQL | (a que o backend já usa) | Reusar a mesma. |
| Token interno do endpoint | `INTERNAL_SYNC_TOKEN` | **Reusar o mesmo** do financeiro — é o token interno do backend, serve pros dois endpoints. Não gere outro. |

> 🚦 **Checkpoint 1.** Confirme que o `PIPEFY_TOKEN` tem acesso ao pipe de Vendas e que o
> `INTERNAL_SYNC_TOKEN` já existente será reusado. Não cria credencial nova.

---

## Fase 2 — Migrations (só o necessário)

As 5 tabelas **já existem** conforme `schema0106.sql` e já têm as `UNIQUE KEY` de
idempotência. **A expectativa é: nenhuma migration necessária.** Antes de concluir isso:

1. Compare o banco vivo com o `schema0106.sql` e confirme que as âncoras existem mesmo
   (`uk_lead_external`, `uk_oportunidade_external`, `uk_oport_phase_event`,
   `uk_dim_lead_origem_raw`, `uk_dim_motivo_perda_raw`).
2. **Lembre da regra de escopo:** migration que **adiciona coluna** está proibida. Só é
   aceitável uma migration que **garanta uma UNIQUE/índice de idempotência que esteja
   faltando** (como foi o caso do `forma_pagamento` no financeiro). Se tudo já existe,
   escreva "nenhuma migration necessária" e siga.

> 🚦 **Checkpoint 2.** Diga ao Davi se há (ou não) lacuna de idempotência. Se houver,
> mostre a ALTER idempotente (padrão `information_schema` + `PREPARE/EXECUTE`, igual à
> `sql/migration_pipefy_financeiro.sql`) e aplique só depois do "ok".

---

## Fase 3 — Introspecção do Pipefy de Vendas (precisa do `PIPEFY_TOKEN`)

> ⚠️ **O print do Kanban NÃO basta.** Ele mostra fases, título (`N #### - Nome`) e
> etiqueta, mas **não** mostra os campos internos do card. O `field_map` sai daqui.

1. Peça ao Davi a **URL ou ID do pipe de Vendas** ("Sales Pipeline").
2. Rode introspecção em `https://api.pipefy.com/graphql` e liste, de cada campo do start
   form e das fases: `id`, `label`, `type`. Liste também as **fases** (id+nome) e as
   **etiquetas/labels** do pipe (pra mapear `oportunidade.coordenacao_id`).
3. Congele os `field.id` em `ingestion/pipefy_comercial/field_map.py` (mapeia por
   `field.id`, nunca por `label`). **Só congele os campos que têm coluna-alvo** — o resto
   ignore, conforme a regra de escopo.

**Mapa provável a validar (ajuste com a introspecção real):**

| Coluna no banco | Origem provável no card |
|---|---|
| `leads.nome` / `email` / `telefone` / `empresa` / `cargo` | campos de contato do start form |
| `leads.external_id` | número do lead (`N ####`) ou id do card |
| `oportunidade.external_id` | id do card |
| `oportunidade.fase_atual_nome` / `fase_atual_id` | fase atual do card |
| `oportunidade.responsaveis` | negociador(es) responsável(is) |
| `oportunidade.valor_fechado` | campo de valor (fase Pré-Assinatura) |
| `oportunidade.origem_id` | FK → `dim_lead_origem` (origem do lead, raw) |
| `oportunidade.motivo_perda_id` | FK → `dim_motivo_perda` (motivo de perda, raw) |
| `oportunidade.coordenacao_id` | **etiqueta/label** do card |
| `oportunidade.status_terminal` | inferido da fase final (fechado/desistido/recusado/postergado) |
| `oportunidade.criado_em` / `finalizado_em` | timestamps do card |
| `oportunidade_phase_history.*` | campo `phases_history` do card (GraphQL) |

> 🚦 **Checkpoint 3.** Mostre a tabela `field.id → coluna`, a lista de fases e a lista de
> etiquetas. Peça validação. Aqui o Davi confirma quais fases significam cada
> `status_terminal` e qual etiqueta mapeia pra qual `coordenacao`.

---

## Fase 4 — Estruturar o módulo (criar o que não existe)

Crie um módulo **isolado**, espelhando o financeiro, **sem tocar** em `ingestion/pipefy/`:

```
ingestion/
  pipefy_comercial/
    __init__.py
    field_map.py        # field.id congelados (Fase 3) — só os que têm coluna
    client.py           # GraphQL paginado (allCards do pipe Vendas) + phases_history
    transform.py        # flatten card → dicts por tabela; extrai eventos de fase
    matching.py         # lead (external_id/email/empresa); dims (raw); coordenacao (etiqueta)
    load.py             # upserts ON DUPLICATE KEY nas 5 tabelas, na ordem das FKs
    sync.py             # orquestra extract→transform→load; retorna resumo
  router.py             # +1 endpoint (ver abaixo) — pode estender o router existente
tests/
  test_transform_comercial.py   # fixture: cards reais do pipe
  test_matching_comercial.py
```

**Regras de carga (respeitando as FKs):**

1. **Ordem:** `dim_lead_origem` + `dim_motivo_perda` → `leads` → `oportunidade` →
   `oportunidade_phase_history`. (Não mexa em `cliente`: `oportunidade.cliente_id` fica
   **NULL** até a oportunidade virar contrato — fora desta automação.)
2. **Idempotência:** todo INSERT é `ON DUPLICATE KEY UPDATE` pela âncora da tabela.
   No MySQL, `rowcount == 1` = insert, `== 2` = update (use isso pros contadores).
3. **Dimensões (raw→canonical):** auto-vivificação. Para cada origem/motivo lido, faça
   `INSERT ... ON DUPLICATE KEY UPDATE` em `dim_*` com `raw_value` + `source_field` e
   **`canonical_value = NULL`** (nunca sobrescreva um canônico que o Davi já preencheu —
   use `COALESCE`/`VALUES` com cuidado). A FK na `oportunidade` aponta pro `id` resolvido.
4. **`leads`:** matching por `uk_lead_external` (source+external_id). Sem clobber de
   campos já preenchidos (COALESCE).
5. **`oportunidade`:** matching por `uk_oportunidade_external`. `coordenacao_id` vem da
   **etiqueta**; `status_terminal` inferido da fase (mapa validado no Checkpoint 3);
   `valor_fechado` só quando existir.
6. **`oportunidade_phase_history`:** a partir do `phases_history` do card, gere 1 linha
   por movimentação, com `external_event_id` estável (ex.: `{card_id}:{phase_id}:{moved_at}`)
   pra idempotência, e calcule `duration_previous_phase_seconds` (diferença entre
   `moved_at` consecutivos). Append-only: nunca apague histórico.
7. **Escopo:** qualquer campo do Pipefy sem coluna-alvo → **descartado** (regra do topo).

**Endpoint de gatilho** (este nome vai pro handoff):
- `POST /internal/sync/pipefy-comercial`
- Exige header `X-Internal-Token` == `INTERNAL_SYNC_TOKEN` (401 se faltar/errado, 500 se
  o backend não tiver o token configurado).
- Querystring `?dry_run=true` → executa tudo mas **não grava**, só loga.
- Resposta JSON:
  `{ "lidos", "inseridos", "atualizados", "fases_registradas", "dims_novas": [...], "erros": [...] }`.
  - `dims_novas` — valores de origem/motivo vistos pela 1ª vez (lembrete pro Davi mapear o
    canônico). É o análogo do `para_revisao` do financeiro.
  - Devolver **207** se `erros` não-vazio (sucesso parcial), igual ao financeiro.

> 🚦 **Checkpoint 4.** Rode `tests/` com cards reais e mostre: o flatten de uma
> oportunidade, os eventos de fase gerados (com duração) e os valores que caíram nas
> `dim_*`, antes de apontar pro banco real.

---

## Fase 5 — Dry-run

Suba o backend localmente e chame `POST /internal/sync/pipefy-comercial?dry_run=true` com
o header interno. Confira: nº de cards lidos, oportunidades e leads montados, eventos de
fase com duração coerente, e `dims_novas`. **Lembre da topologia:** o banco de produção só
é alcançável da VPS — o dry-run local **não grava** (ideal pra validar transform). O sync
real (sem `dry_run`) roda na VPS. Só depois do "ok" do Davi, rode sem `dry_run`.

---

## Fase 6 — Escrever o `HANDOFF_FLUXO_VENDAS.md`

Crie, na raiz do repo, `HANDOFF_FLUXO_VENDAS.md` com **exatamente** estas infos — é o que
o agent do fluxo n8n vai ler:

```markdown
# Handoff Backend → Fluxo n8n (Vendas)

## Endpoint de sync
- Método/rota: POST /internal/sync/pipefy-comercial
- URL base (produção): https://banco-de-dados-backend.d86ysa.easypanel.host
  - Local (dev): http://localhost:8000
- Querystring opcional: ?dry_run=true  (testar sem gravar)

## Autenticação
- Header obrigatório: X-Internal-Token
- Valor: o INTERNAL_SYNC_TOKEN do backend (o MESMO já usado no fluxo financeiro).
  NÃO está neste arquivo (segredo). Sem header/errado → 401.

## Corpo da requisição
- Nenhum.

## Resposta (JSON)
- { "lidos", "inseridos", "atualizados", "fases_registradas", "dims_novas": [...], "erros": [...] }
- Considerar erro: status != 2xx OU "erros" não-vazio (207 = sucesso parcial).
- "dims_novas" não-vazio NÃO é erro — é só lembrete de mapear canônico; pode ir no resumo.

## Observações pro agent do fluxo
- Token do Pipefy NÃO entra no n8n — fica no backend.
- Credencial Header Auth do INTERNAL_SYNC_TOKEN: a MESMA do fluxo financeiro pode ser reusada.
- Credencial Microsoft (Outlook/Graph) já existe no n8n — reusar.
- Frequência sugerida do Schedule: <preencher>
```

Preencha o que souber e deixe `<preencher>` no que depende do Davi (frequência). **Nunca**
escreva o valor do `INTERNAL_SYNC_TOKEN`.

> 🚦 **Checkpoint 6.** Avise o Davi que o `HANDOFF_FLUXO_VENDAS.md` foi gerado e que ele já
> pode rodar o agent do fluxo apontando pra esse arquivo.

---

## Decisões fechadas (não reabrir)
- **Escopo:** só popular as 5 tabelas comerciais existentes, só colunas existentes; campo
  sem coluna é descartado; proibido criar tabela/coluna.
- **Histórico de fase:** o backend puxa o `phases_history` via GraphQL e calcula a duração
  (n8n fino). Nada de webhook.
- **Dimensões:** auto-vivificar `raw_value` com `canonical_value = NULL`; o Davi padroniza
  o canônico à mão depois.
- **`cliente_id` da oportunidade:** fica NULL até virar contrato (fora desta automação).
- **`coordenacao_id`:** vem da etiqueta do card.
- **Token Pipefy e `INTERNAL_SYNC_TOKEN`:** reusar os do financeiro (mesma conta/backend).
- **Fonte:** Pipefy GraphQL via Service Account (PAT deprecado).
- **Arquitetura:** n8n fino + lógica em Python aqui no backend, espelhando `ingestion/pipefy/`.
```
