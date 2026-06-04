# Handoff Backend → Fluxo n8n (Controle Contábil)

> Gerado pelo agent de BACKEND. É o contrato que o agent do fluxo n8n deve seguir para
> disparar a ingestão da **planilha Controle Contábil** (caixa livre, hospedada no
> SharePoint/Excel Online). Toda a lógica pesada (parsing do `.xlsx`, normalização,
> seed de categorias, matching, upsert idempotente) vive no backend.
>
> **Diferença em relação aos fluxos de Pipefy:** o backend **não** acessa o SharePoint.
> É o **n8n** que baixa o arquivo (com a credencial Microsoft Graph que já existe) e o
> **envia no corpo** da requisição. O n8n ganha um passo a mais (download) antes do POST.

## Endpoint de sync
- **Método/rota:** `POST /internal/sync/controle-contabil`
- **URL base (produção):** `https://banco-de-dados-backend.d86ysa.easypanel.host`
  - Local (dev): `http://localhost:8000`
  - Chamada completa: `POST https://banco-de-dados-backend.d86ysa.easypanel.host/internal/sync/controle-contabil`
- **Querystring opcional:** `?dry_run=true` → executa tudo mas **não grava** (só loga).

## Corpo da requisição (≠ Pipefy)
- **`multipart/form-data`** com o campo **`file`** = o binário do `.xlsx`.
- Content-Type do arquivo:
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- No n8n: o nó Microsoft Graph baixa o arquivo; o nó HTTP Request envia esse binário no
  campo `file` (Body Content Type = `n8n Binary File` / `multipart-form-data`).

## Autenticação
- **Header obrigatório:** `X-Internal-Token`
- **Valor:** o `INTERNAL_SYNC_TOKEN` do backend — **o MESMO já usado nos fluxos de Pipefy.**
  Não está neste arquivo (segredo). Sem header/errado → `401`; backend sem o token → `500`.
  - No n8n, **reusar a credencial Header Auth** que já existe.

## De onde o n8n baixa o arquivo
- Arquivo no SharePoint/Excel Online: **`<preencher: site / drive / caminho ou ID do arquivo>`**
- O n8n baixa via **Microsoft Graph (credencial JÁ existente)** e envia no corpo.
  O backend nunca toca no SharePoint.

## Resposta (JSON)
```json
{
  "lidos": 700,
  "ignorados": 0,
  "inseridos": 0,
  "atualizados": 0,
  "categorias_criadas": 53,
  "para_revisao": ["sem categoria — linha 17 (2026-05-29, ...)", "..."],
  "erros": ["linha <data>/<external_id>: <mensagem>"]
}
```
- `lidos` — linhas de transação lidas da planilha (só as que têm data de verdade).
- `ignorados` — linhas não gravadas por faltar campo obrigatório (conta/tipo/valor) ou
  conta inexistente em `conta_bancaria`.
- `inseridos` / `atualizados` — transações novas vs. já existentes (idempotência por
  `external_id`). Numa 2ª rodada sem mudanças, `inseridos` deve ser ~0.
- `categorias_criadas` — categorias novas semeadas em `categoria_transacao` nesta rodada.
- `para_revisao` — linhas que entraram (ou foram puladas) mas precisam de olho do Davi
  (categoria vazia, setor desconhecido, conta inexistente). **NÃO é erro.**
- `erros` — falhas por linha; o resto continua.

### Como o n8n deve interpretar
- **HTTP 200** → tudo certo.
- **HTTP 207** (Multi-Status) → rodou, mas `erros` não-vazio (sucesso parcial).
- **Considerar erro:** status `!= 2xx` **OU** array `erros` não-vazio → notificar.
- `para_revisao` não-vazio **não** dispara erro (é esperado: ~102 linhas hoje sem categoria).

## ⚠️ Observações pro agent do fluxo
- **Dois nós usam a credencial Microsoft Graph existente:** (1) baixar o `.xlsx`,
  (2) notificar em caso de erro. Não recriar.
- **Timeout:** parsear ~700 linhas + gravar leva alguns segundos — um timeout de
  `120000` ms (2 min) é folgado. Use `neverError: true` + `fullResponse: true` pra ler
  `statusCode`/`body`.
- **Frequência sugerida do Schedule:** **1x/dia** — a planilha é atualizada à mão pelas
  analistas. Ajuste com o Davi. *(<preencher a frequência final>)*
- **Endpoint público** (atrás do domínio EasyPanel), protegido só pelo `X-Internal-Token`.
- Vale listar `para_revisao` no e-mail de resumo pra o Davi padronizar categorias/setores.
- **Primeiro teste com `?dry_run=true`:** confira `lidos` ~700 e `erros: []` antes de
  deixar gravar.
