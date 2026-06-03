# Handoff Backend → Fluxo n8n (Vendas / Comercial)

> Gerado pelo agent de BACKEND. É o contrato que o agent do fluxo n8n deve seguir para
> disparar a ingestão do **Pipefy de Vendas (Sales Pipeline, 734299)**. Toda a lógica pesada
> (GraphQL, transform, matching, upsert, cálculo de duração de fase) vive no backend — o n8n
> só agenda e chama.

## Endpoint de sync
- **Método/rota:** `POST /internal/sync/pipefy-comercial`
- **URL base (produção):** `https://banco-de-dados-backend.d86ysa.easypanel.host`
  - Local (dev): `http://localhost:8000`
  - Chamada completa: `POST https://banco-de-dados-backend.d86ysa.easypanel.host/internal/sync/pipefy-comercial`
- **Querystring opcional:** `?dry_run=true` → executa tudo mas **não grava** (só loga).

## Autenticação
- **Header obrigatório:** `X-Internal-Token`
- **Valor:** o `INTERNAL_SYNC_TOKEN` do backend — **o MESMO já usado no fluxo financeiro.**
  Não está neste arquivo (segredo). Sem header/errado → `401`; backend sem o token → `500`.
  - No n8n, **reusar a credencial Header Auth** que já existe pro financeiro.

## Corpo da requisição
- **Nenhum.** Não enviar body.

## Resposta (JSON)
```json
{
  "lidos": 2381,
  "inseridos": 0,
  "atualizados": 0,
  "fases_registradas": 0,
  "dims_novas": ["origem[ld]: <valor novo>", "motivo[<campo>]: <valor novo>"],
  "erros": ["card <id>: <mensagem>"]
}
```
- `lidos` — cards lidos do Pipefy.
- `inseridos` / `atualizados` — **oportunidades** criadas vs. já existentes (idempotência por `external_id`).
- `fases_registradas` — eventos novos gravados no histórico de fase.
- `dims_novas` — origens/motivos vistos pela 1ª vez. **NÃO é erro** — é lembrete pro Davi
  mapear o `canonical_value` à mão depois. Pode ir no corpo do e-mail de resumo.
- `erros` — falhas por card; o resto continua.

### Como o n8n deve interpretar
- **HTTP 200** → tudo certo.
- **HTTP 207** (Multi-Status) → rodou, mas `erros` não-vazio (sucesso parcial).
- **Considerar erro:** status `!= 2xx` **OU** array `erros` não-vazio → notificar.
- `dims_novas` não-vazio **não** dispara erro.

## ⚠️ Observações pro agent do fluxo (importante!)
- **Volume alto:** este pipe tem **~2.381 cards** (o financeiro tinha 16). A sincronização
  faz muitas escritas e **pode levar vários minutos**. Configure um **timeout generoso no nó
  HTTP Request — recomendo `300000` ms (5 min) ou mais**, bem acima dos 120 s do fluxo
  financeiro. Use `neverError: true` + `fullResponse: true` (igual ao financeiro) pra ler
  `statusCode`/`body` mesmo se algo escapar.
- **Frequência sugerida do Schedule:** **1x/dia** (ex.: 06:00). É idempotente, mas pelo volume
  não vale rodar de hora em hora. Ajuste com o Davi. *(<preencher a frequência final>)*
- O **token do Pipefy NÃO entra no n8n** — fica só no backend (`PIPEFY_TOKEN`, o mesmo do financeiro).
- Credencial **Microsoft (Outlook/Graph) já existe** — reusar pra notificação.
- **Endpoint público** (atrás do domínio EasyPanel), protegido só pelo `X-Internal-Token`.
- Em caso de `dims_novas` não-vazio, vale listar os valores no e-mail pra o Davi padronizar
  o `canonical_value` em `dim_lead_origem` / `dim_motivo_perda`.
