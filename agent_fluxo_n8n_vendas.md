# Runbook do Agent de FLUXO (n8n) — Ingestão Pipefy de Vendas (Comercial)

> **Para o agent:** sua missão é escrever o **JSON de um workflow n8n** que o Davi vai
> importar, perguntando antes as chaves que precisar. Você depende do **agent de backend**,
> que roda ANTES e deixa o `HANDOFF_FLUXO_VENDAS.md` com rota, URL e auth. Siga as fases na
> ordem. **Pare nos checkpoints 🚦.** Sempre responda em português.
>
> **"Criar o n8n" = escrever o `.json` do workflow.** Você não roda o n8n; entrega o
> arquivo pro Davi importar.
>
> **Existe um precedente:** já há um workflow do **Pipefy Financeiro**
> (`pipefy_financeiro_sync.n8n.json`): Schedule → HTTP Request → IF → Microsoft Outlook +
> NoOp + Sticky Note. **Espelhe-o** — é o mesmo desenho, só muda a rota e os textos.

---

## Arquitetura (n8n fino)

O backend já faz todo o trabalho pesado (puxar do Pipefy de Vendas, transformar, calcular
duração de fase, gravar no MySQL) atrás de um endpoint. **Seu workflow é enxuto:** agenda →
chama o endpoint → notifica se der erro. Você **NÃO precisa do token do Pipefy nem do
MySQL** — isso vive no backend. Não peça essas chaves.

```
[Schedule] → [HTTP Request → POST /internal/sync/pipefy-comercial] → [IF erro] → [Outlook: alerta]
```

---

## Fase 0 — Ler o handoff do backend

1. Procure `HANDOFF_FLUXO_VENDAS.md` na pasta.
2. **Se não existir:** PARE. Diga ao Davi que o agent de backend precisa rodar primeiro pra
   gerar esse arquivo. Não invente o endpoint.
3. Se existir, extraia: método+rota, URL base, header de auth, formato da resposta, o que
   conta como erro, e a frequência sugerida.

> 🚦 **Checkpoint 0.** Resuma ao Davi o que leu (qual endpoint vai chamar, qual header, como
> detecta erro). Note a diferença pro financeiro: a resposta tem `fases_registradas` e
> `dims_novas` (este último **não é erro** — é lembrete de mapear canônico).

---

## Fase 1 — Chaves que o FLUXO precisa

Conduza o Davi. São poucas (n8n fino). **Nada de segredo colado no chat.**

| O que | Onde vive | O que o Davi faz |
|---|---|---|
| **URL base do backend** | parâmetro do nó HTTP | Produção: `https://banco-de-dados-backend.d86ysa.easypanel.host` (mesma do financeiro) |
| **Token interno** (`X-Internal-Token`) | **credencial Header Auth no n8n** | **Reusar a credencial já criada pro fluxo financeiro** — é o mesmo `INTERNAL_SYNC_TOKEN`. Não criar outra. |
| **Microsoft (Outlook/Graph)** | n8n | ✅ **já existe.** Só selecionar no nó de notificação. |
| **Frequência do Schedule** | nó Schedule | Confirmar (pode ser igual ao financeiro, ex.: 2x/dia 09h e 18h, ou outra) |

> 🚦 **Checkpoint 1.** Confirme: URL base, credencial Header Auth reusada, credencial
> Microsoft existente, e a frequência. O token do Pipefy NÃO entra aqui.

---

## Fase 2 — Escrever o JSON do workflow

Monte o `.json` com estes nós (espelhe `pipefy_financeiro_sync.n8n.json`):

1. **Schedule Trigger** — na frequência da Fase 1 (cron).
2. **HTTP Request**
   - `POST {URL_BASE}/internal/sync/pipefy-comercial` (rota exata do handoff).
   - Autenticação: `predefinedCredentialType` → `httpHeaderAuth`, referenciando a
     credencial Header Auth (`X-Internal-Token`). **Não** escreva o valor do token.
   - `options.response`: `fullResponse: true` e `neverError: true` (pra o IF ler o
     `statusCode` e o `body` mesmo em erro). Timeout generoso (ex.: 120000 ms).
3. **IF** — marca erro quando `statusCode >= 300` **OU** `($json.body.erros || []).length > 0`
   (combinator `or`). **Não** trate `dims_novas` como erro.
4. **Microsoft Outlook** (ramo de erro) — e-mail com o resumo: `statusCode`, `lidos`,
   `inseridos`, `atualizados`, `fases_registradas`, e a lista `dims_novas` (valores novos de
   origem/motivo pra mapear). Destinatário: o mesmo do financeiro (`ti@metaconsultoria.com`,
   confirmar). Referencie a credencial Microsoft **existente**; avise que o Davi reaponta na
   importação.
5. **NoOp "Sync OK"** no ramo sem erro.
6. **Sticky Note** com os reapontamentos da importação.

Regras do JSON:
- **Zero segredos embutidos.** Token vai por credencial.
- URL de produção pode vir fixa no nó (igual ao financeiro), fácil de trocar pra local.
- A Sticky Note deve listar: (1) credencial Header Auth do token interno **(a mesma do
  financeiro)**, (2) credencial Microsoft existente, (3) conferir a `URL_BASE`. Lembre que o
  n8n importa só a referência da credencial, nunca o segredo.
- Nomeie o workflow algo como **"Pipefy Vendas → MySQL Sync"** e use tags
  `["comercial", "vendas", "pipefy", "sync"]`. Salve como `pipefy_vendas_sync.n8n.json`.

> 🚦 **Checkpoint 2.** Antes de finalizar, mostre ao Davi a estrutura dos nós e os pontos de
> reapontamento na importação.

---

## Fase 3 — Entrega e teste

1. Entregue o `.json` pro Davi importar no n8n.
2. Importar → reapontar as 2 credenciais → conferir `URL_BASE`.
3. **Primeiro teste com segurança:** rode manual com `?dry_run=true` na URL do HTTP Request,
   confira que a resposta traz os `lidos` esperados e nenhum `erros`.
4. Só depois tire o `dry_run`, rode manual uma vez, confira o banco (use selects de
   verificação) e então **ative o Schedule**.

---

## Decisões fechadas (não reabrir)
- Arquitetura: n8n fino — workflow só agenda, dispara e notifica.
- Token do Pipefy e MySQL: no backend, não no n8n.
- Credencial Header Auth do token interno e credencial Microsoft: **reusar as existentes**.
- `dims_novas` na resposta **não é erro** — é lembrete de mapeamento canônico.
- Autenticação do endpoint: header `X-Internal-Token`.
- Fonte de verdade do contrato entre agents: `HANDOFF_FLUXO_VENDAS.md`.
```
