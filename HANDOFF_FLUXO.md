# Handoff Backend → Fluxo n8n

> Gerado pelo agent de BACKEND. É o contrato que o agent do fluxo n8n deve seguir
> para disparar a ingestão do Pipefy Financeiro. Toda a lógica pesada (GraphQL do
> Pipefy, transformação, matching, upsert) vive no backend — o n8n só agenda e chama.

## Endpoint de sync
- **Método/rota:** `POST /internal/sync/pipefy-financeiro`
- **URL base (produção):** `https://banco-de-dados-backend.d86ysa.easypanel.host`
  - Local (dev): `http://localhost:8000`
  - Chamada completa: `POST https://banco-de-dados-backend.d86ysa.easypanel.host/internal/sync/pipefy-financeiro`
- **Querystring opcional:** `?dry_run=true` → executa tudo mas **não grava** (só loga). Útil pra teste.

## Autenticação
- **Header obrigatório:** `X-Internal-Token`
- **Valor:** o conteúdo de `INTERNAL_SYNC_TOKEN` do `.env` do backend.
  - O Davi copia esse valor pra uma credencial **Header Auth** no n8n. **NÃO está neste arquivo** (é segredo).
  - Sem o header (ou com valor errado) → `401`. Se o backend estiver sem `INTERNAL_SYNC_TOKEN` configurado → `500`.

## Corpo da requisição
- **Nenhum.** Não enviar body.

## Resposta (JSON)
```json
{
  "lidos": 16,
  "inseridos": 0,
  "atualizados": 0,
  "para_revisao": ["<card_id>", "..."],
  "erros": ["card <id>: <mensagem>", "..."]
}
```
- `lidos` — quantos cards vieram do Pipefy.
- `inseridos` / `atualizados` — contratos criados vs. já existentes (idempotência por `external_id`).
- `para_revisao` — card_ids com "Possui Valor Variável" = Sim (parcelas não divididas automaticamente).
- `erros` — falhas por card; o resto continua.

### Como o n8n deve interpretar
- **HTTP 200** → tudo certo.
- **HTTP 207** (Multi-Status) → rodou, mas `erros` não está vazio (sucesso parcial).
- **Considerar erro:** status `!= 2xx` **OU** array `erros` não-vazio → notificar.

## Observações pro agent do fluxo
- O **token do Pipefy NÃO é necessário no n8n** — fica só no backend (`PIPEFY_TOKEN`).
- Credencial **Microsoft Graph já existe** no n8n do Davi; reusar pra notificação de erro/resumo.
- **Frequência sugerida do Schedule:** diária às 6h (o sync é idempotente, pode rodar quantas vezes quiser; ajuste se quiser mais/menos frequente).
- **Endpoint é público** (atrás do domínio do EasyPanel), protegido só pelo `X-Internal-Token`. O n8n chama a URL pública direto — não precisa estar na mesma rede.
- Em caso de `para_revisao` não-vazio, vale incluir os card_ids na notificação pra revisão manual das parcelas variáveis.
