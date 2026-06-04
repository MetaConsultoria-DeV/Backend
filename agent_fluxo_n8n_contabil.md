# Runbook do Agent de FLUXO (n8n) — Ingestão Controle Contábil

> **Para o agent:** sua missão é escrever o **JSON de um workflow n8n** que o Davi vai
> importar, perguntando antes todas as chaves que precisar. Você depende do **agent de
> backend**, que roda ANTES e deixa `HANDOFF_FLUXO_CONTABIL.md` com a rota, a URL, o
> esquema de auth e o ID do arquivo no SharePoint. Siga as fases na ordem. **Pare nos
> checkpoints 🚦.** Sempre responda em português.
>
> **"Criar o n8n" = escrever o `.json` do workflow.** Você não roda o n8n; entrega o
> arquivo pro Davi importar.

---

## Arquitetura (n8n fino, mas aqui ele BAIXA o arquivo)

Diferença para os fluxos de Pipefy: lá o n8n só agendava e chamava um endpoint que puxava
da API. **Aqui a fonte é um arquivo no SharePoint**, e quem tem a credencial Microsoft
Graph é o n8n. Então o seu workflow tem um passo a mais: **baixar o `.xlsx` e enviá-lo no
corpo** da requisição ao backend. O backend faz todo o parsing/transformação/gravação.

```
[Schedule] → [Microsoft Graph: baixar .xlsx] → [HTTP Request: POST .xlsx → backend]
           → [IF erro] → [Microsoft Graph: alerta]
```

Você **não** precisa do MySQL nem de lógica de planilha — isso vive no backend. Você
precisa da credencial Graph (já existe) para **baixar** o arquivo e para **alertar**.

---

## Fase 0 — Ler o handoff do backend

1. Procure `HANDOFF_FLUXO_CONTABIL.md` na pasta do backend.
2. **Se não existir:** PARE. Diga ao Davi que o agent de backend precisa rodar primeiro
   pra gerar esse arquivo. Não invente o endpoint nem o ID do arquivo.
3. Se existir, extraia: método+rota, URL base, como o corpo deve ir (multipart `file`),
   header de auth, **o ID/caminho do arquivo no SharePoint**, formato da resposta, o que
   conta como erro e a frequência sugerida.

> 🚦 **Checkpoint 0.** Devolva ao Davi um resumo do que leu (qual endpoint, qual header,
> qual arquivo baixar, como detecta erro). Confirme antes de seguir.

---

## Fase 1 — Chaves que o FLUXO precisa (pergunte tudo aqui)

| O que | Onde vive | O que o Davi faz |
|---|---|---|
| **URL base do backend** | variável/parâmetro do workflow | Informar (local `http://localhost:PORTA` ou produção `https://...`) |
| **Token interno** (`X-Internal-Token`) | **credencial Header Auth no n8n** | Reusar a credencial que já criou para os syncs de Pipefy (mesmo `INTERNAL_SYNC_TOKEN`) |
| **Microsoft Graph** | n8n | ✅ **já existe.** Usada em DOIS nós: baixar o arquivo e alertar. Não recriar |
| **Arquivo no SharePoint** | nó Graph de download | Confirmar site/drive/ID do arquivo (vem do handoff; o Davi valida) |
| **Frequência do Schedule** | nó Schedule | Confirmar (sugestão: 1x/dia; a planilha é atualizada à mão pelas analistas) |

> 🚦 **Checkpoint 1.** Confirme: URL base? Credencial Header Auth do token (reusada)?
> Arquivo certo no SharePoint? Frequência? O MS Graph ele já tem. O token do backend NÃO
> entra no JSON — só a referência da credencial.

---

## Fase 2 — Escrever o JSON do workflow

Monte o `.json` com estes nós:

1. **Schedule Trigger** — na frequência confirmada.
2. **Microsoft Graph (download)** — baixa o `.xlsx` do SharePoint usando a credencial
   existente e o ID/caminho do handoff. Saída = binário do arquivo.
3. **HTTP Request**
   - `POST {{URL_BASE}}/internal/sync/controle-contabil` (rota exata do handoff).
   - **Corpo:** `multipart-form-data`, campo `file` = o binário vindo do nó anterior.
     Content-Type do arquivo: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
   - Autenticação: referencie a **credencial Header Auth** (`X-Internal-Token`). **Não**
     escreva o valor do token no JSON.
   - Timeout generoso (parsear ~700 linhas + gravar leva alguns segundos).
4. **IF** — marca erro quando status != 2xx OU `erros` da resposta não-vazio.
5. **Microsoft Graph (alerta)** (ramo de erro) — envia e-mail/mensagem com o resumo da
   resposta. Referencie a credencial Graph **existente**.

Regras do JSON:
- **Zero segredos embutidos.** Token e (se sensível) URL vão por credencial/variável.
- `URL_BASE` fácil de trocar entre local e produção.
- **Sticky Note** listando os reapontamentos na importação: (1) credencial Header Auth do
  token interno (a mesma do Pipefy), (2) credencial Microsoft Graph existente — usada nos
  **dois** nós Graph, (3) conferir `URL_BASE`, (4) conferir o arquivo do SharePoint.

> 🚦 **Checkpoint 2.** Antes de finalizar, mostre ao Davi a estrutura dos nós (com o passo
> de download) e os pontos de reapontamento na importação.

---

## Fase 3 — Entrega e teste

1. Entregue o `.json` pro Davi importar.
2. Importação: importar → reapontar credenciais (Header Auth + Graph nos 2 nós) →
   conferir `URL_BASE` e o arquivo do SharePoint.
3. **Primeiro teste com segurança:** rode manual apontando o HTTP Request pra
   `...controle-contabil?dry_run=true`. Confira que a resposta traz `lidos` ~701 e nenhum
   erro, **sem gravar**.
4. Só depois tire o `dry_run`, rode manual uma vez, confira no banco que `transacao` e
   `categoria_transacao` foram populadas, e então ative o Schedule.

---

## Decisões fechadas (não reabrir)
- Arquitetura: n8n fino — agenda, **baixa o arquivo**, dispara o endpoint e notifica.
- O parsing/transformação/gravação é do backend; n8n não toca MySQL nem lê a planilha.
- Microsoft Graph: credencial já existente, reusada para baixar E para alertar.
- Token do backend: via credencial Header Auth (a mesma do Pipefy), nunca no JSON.
- Corpo da requisição: o `.xlsx` em multipart `file`.
- Fonte de verdade do contrato entre agents: `HANDOFF_FLUXO_CONTABIL.md`.
