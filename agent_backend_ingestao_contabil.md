# Runbook do Agent de BACKEND — Ingestão Controle Contábil

> **Para o agent:** você roda dentro da pasta do backend FastAPI do Davi. Sua missão:
> (1) estruturar a ingestão da **planilha Controle Contábil** (Excel do SharePoint) para
> as tabelas `categoria_transacao` e `transacao`, (2) criar **migrations** só se forem
> necessárias, (3) no final, escrever `HANDOFF_FLUXO_CONTABIL.md` — o contrato que o
> **outro agent (o do fluxo n8n)** vai ler. Siga as fases na ordem. **Pare nos
> checkpoints 🚦 e espere a resposta do Davi.** Sempre responda em português.
>
> **Ordem do projeto:** este agent roda PRIMEIRO. O agent do fluxo n8n roda DEPOIS, e
> depende do seu `HANDOFF_FLUXO_CONTABIL.md`. Não é você quem cria o JSON do n8n.

---

## Arquitetura (n8n fino, fonte = arquivo)

Diferença para os syncs de Pipefy: a fonte **não é uma API**, é um **arquivo `.xlsx`**.
Quem tem a credencial do SharePoint (Microsoft Graph) é o **n8n**, que já a possui. Então
o fluxo é: **n8n baixa o arquivo e faz POST do `.xlsx` para o seu endpoint**; você recebe
os bytes, parseia com `openpyxl`, transforma e grava. Logo, **o backend NÃO precisa de
credencial do SharePoint/Graph** — só recebe o arquivo e o `INTERNAL_SYNC_TOKEN`.

Toda a lógica pesada é sua, em Python testável: parsear a planilha, normalizar setores e
categorias, fazer matching de projeto, semear categorias e fazer upsert idempotente.

---

## Fase 0 — Reconhecimento (antes de escrever qualquer linha)

Leia, nesta ordem:
1. `sql/schemateste0406.sql` — as tabelas-alvo `categoria_transacao` e `transacao`, suas
   FKs e a `UNIQUE KEY uk_transacao_external (external_source, external_id)`. Confira
   também `conta_bancaria` e `celula` (já populadas — referência) e `projeto_externo`.
2. `plano_ingestao_controle_contabil.md` — **fonte de verdade** do mapeamento
   campo→tabela, normalizações, seed de categorias, hash de `external_id` e decisões
   fechadas. Implemente a partir dele; não reinvente regra.
3. O backend existente, espelhando os syncs que já existem:
   - `ingestion/pipefy/` e `ingestion/pipefy_comercial/` (estrutura client/transform/
     matching/load/sync), `ingestion/router.py` (padrão do endpoint + `X-Internal-Token`),
     `database.py` (pool MySQL, `execute_query`, `execute_insert`, `transaction()`),
     `main.py` (como o router é montado), `tests/`.

> 🚦 **Checkpoint 0.** Devolva ao Davi: confirmação do padrão (SQL cru via
> `mysql.connector`, módulo por fonte, router compartilhado), e a lista do que **já
> existe** vs. o que vai **criar**. Espere o "ok".

---

## Fase 1 — Credenciais que o BACKEND possui

Bem menos que no Pipefy, porque o backend não fala com o SharePoint.

| Credencial | Var no `.env` | O que fazer |
|---|---|---|
| Conexão MySQL | (a que o backend já usa) | Reusar a mesma do pool existente |
| Token interno do endpoint | `INTERNAL_SYNC_TOKEN` | **Já existe** (mesmo dos syncs de Pipefy). Reusar o mesmo valor — o n8n já manda esse header |

**Não há** token de Pipefy nem credencial de SharePoint aqui. O arquivo chega por upload.

> 🚦 **Checkpoint 1.** Confirme com o Davi que vai **reusar** o `INTERNAL_SYNC_TOKEN`
> existente (não gerar outro) e a conexão MySQL atual.

---

## Fase 2 — Migrations (provavelmente nenhuma)

As tabelas `categoria_transacao` e `transacao` **já existem** no schema. Sua tarefa NÃO é
recriá-las. É:

1. Comparar o banco vivo com `sql/schemateste0406.sql` e achar **lacunas reais**.
2. Garantir as âncoras de idempotência (não recriar se já houver):
   - `transacao`: `uk_transacao_external (external_source, external_id)`.
   - `categoria_transacao`: `uk_categoria_transacao_nome (nome)`.
3. Use a ferramenta de migration que o backend já usa. Gere a migration, **não aplique
   ainda**. Se não houver lacuna, diga "nenhuma migration necessária" e siga.

> 🚦 **Checkpoint 2.** Mostre ao Davi o diff banco↔schema e, se houver, o conteúdo da
> migration. Aplique só depois do "ok".

---

## Fase 3 — Entender a planilha de verdade (use o arquivo de exemplo)

Há uma cópia local: `Controle Contábil.xlsm`. Use-a como fixture para desenvolver, **mas
o parser deve achar a tabela por âncora, não por índice fixo** (as analistas inserem
linhas). Confirme, lendo o arquivo:

1. O cabeçalho real (`Data | Conta | Entrada/Saída | Setor | Categoria | Nº do Projeto |
   Valor | Observações`) aparece **duas vezes**; a tabela válida é a segunda (a que tem
   `mm/aaaa | Real | Acumulado` à direita). Localize-a varrendo as colunas D–K por esses
   rótulos normalizados.
2. Extraia os **valores distintos** de Conta, Setor, Categoria e Tipo para validar as
   tabelas de normalização do plano (§3 e §4). Reporte qualquer valor novo que o plano
   não preveja.

> 🚦 **Checkpoint 3.** Mostre ao Davi: linha de cabeçalho detectada, contagem de
> transações lidas, e os distintos de Setor/Categoria/Conta com a tradução proposta
> (incluindo "Área Comercial → MKTV?" e categorias suspeitas de typo). Peça validação.

---

## Fase 4 — Estruturar o módulo (criar o que não existe)

Crie um módulo isolado, no mesmo molde dos de Pipefy:

```
ingestion/
  contabil/
    __init__.py
    parser.py      # openpyxl: bytes do .xlsx → lista de dicts (1 por linha da tabela)
    normalize.py   # setor→celula, categoria (trim/colapsa/casefold), tipo, valor abs
    matching.py    # projeto_externo por código NNN.YYYY; lookups de conta/celula/categoria
    transform.py   # linha crua → dict de transacao + external_id (hash+contador)
    seed.py        # deriva categoria_transacao dos distintos (tipo/celula inferidos)
    load.py        # upserts ON DUPLICATE KEY: categoria_transacao → transacao
    sync.py        # orquestra parse→seed→transform→load; retorna resumo
tests/
  test_contabil_parser.py     # fixture: a planilha de exemplo
  test_contabil_normalize.py  # setores sujos, categorias com typo/espaço, vazias
  test_contabil_transform.py  # external_id estável + contador de duplicatas
```

Regras (detalhe completo no `plano_ingestao_controle_contabil.md`):
- **Ordem de carga:** `categoria_transacao` → `transacao` (FK).
- **Idempotência:** todo INSERT é `ON DUPLICATE KEY UPDATE`.
  `external_id = sha1(data|conta|tipo|setor|categoria|valor|obs)[:16] + "-" + ocorrência`,
  contador na ordem de leitura da planilha (§5 do plano).
- **conta_id:** lookup em `conta_bancaria.nome`; sem conta → `para_revisao`, não grava.
- **celula_id:** normaliza setor e mapeia; "Gerais"/desconhecido → `NULL` (§3).
- **categoria_id:** lookup na `categoria_transacao` semeada; vazia/ambígua → `NULL` +
  `para_revisao`.
- **projeto_externo_id:** código `NNN.YYYY` casando em `projeto_externo.codigo`; senão
  `NULL`. **Nunca cria projeto.**
- **valor:** `abs()`; sinal vive no `tipo`.
- **`contrato_pagamento_id`:** sempre `NULL` (fora desta automação).
- **Linha sem data válida** (ou rodapé/linha-resumo) → descartar, não é transação.

**Endpoint de gatilho** (nome que vai pro handoff):
- `POST /internal/sync/controle-contabil`
- Recebe o arquivo `.xlsx` no corpo (multipart `file`, `UploadFile` do FastAPI).
- Exige header `X-Internal-Token == INTERNAL_SYNC_TOKEN` (401 se faltar/errar).
- `?dry_run=true` → executa tudo mas **não grava**, só loga.
- Resposta JSON: `{ "lidos", "ignorados", "inseridos", "atualizados",
  "categorias_criadas", "para_revisao": [...], "erros": [...] }`.
- Monte no `ingestion/router.py` ao lado dos endpoints `pipefy-financeiro` e
  `pipefy-comercial`, reusando o `_check_token`.

> 🚦 **Checkpoint 4.** Rode `tests/` com a planilha de exemplo e mostre: nº de transações,
> categorias derivadas (com tipo/celula), amostra de `external_id`, e a prova de que rodar
> duas vezes não duplica (mesmo `external_id`). Mostre quem caiu em `para_revisao`.

---

## Fase 5 — Dry-run com o arquivo real

Suba o backend localmente e faça `POST /internal/sync/controle-contabil?dry_run=true`
enviando o `.xlsx` de exemplo no corpo, com o header interno. Confira: ~701 lidos,
categorias semeadas plausíveis, ninguém com conta/tipo faltando virando insert, e a lista
de `para_revisao`. Só depois do "ok" do Davi, rode **sem** `dry_run` (grava de verdade) e
confira no banco que `transacao` e `categoria_transacao` deixaram de estar vazias.

> 🚦 **Checkpoint 5.** Mostre ao Davi o resumo do dry-run e o do run real (linhas
> gravadas em cada tabela). Confirme idempotência rodando 2x e mostrando `inseridos: 0`
> na segunda.

---

## Fase 6 — Escrever o `HANDOFF_FLUXO_CONTABIL.md`

Crie, na raiz do backend, o arquivo com **exatamente** estas infos — é o que o agent do
fluxo n8n vai ler:

```markdown
# Handoff Backend → Fluxo n8n (Controle Contábil)

## Endpoint de sync
- Método/rota: POST /internal/sync/controle-contabil
- URL base: <preencher: local http://localhost:PORTA ; produção https://...>
- Corpo: o arquivo .xlsx (multipart form-data, campo "file")
- Querystring opcional: ?dry_run=true  (testar sem gravar)

## Autenticação
- Header obrigatório: X-Internal-Token
- Valor: o conteúdo de INTERNAL_SYNC_TOKEN do .env do backend
  (o mesmo já usado pelos syncs de Pipefy; o Davi reusa a credencial Header Auth do n8n)

## De onde o n8n tira o arquivo
- Arquivo no SharePoint/Excel Online: <preencher: site/drive/caminho ou ID do arquivo>
- O n8n baixa via Microsoft Graph (credencial JÁ existente) e envia no corpo.

## Resposta (JSON)
- { "lidos", "ignorados", "inseridos", "atualizados", "categorias_criadas",
    "para_revisao": [...], "erros": [...] }
- Considerar erro: status != 2xx OU "erros" não-vazio

## Observações pro agent do fluxo
- O backend NÃO acessa o SharePoint: é o n8n que baixa o .xlsx e faz upload.
- Credencial Microsoft Graph já existe no n8n; reusar para baixar o arquivo E para alertar.
- Frequência sugerida do Schedule: <preencher>
```

Preencha o que souber (rota, formato da resposta) e deixe placeholders (`<preencher>`) no
que depende do Davi (URL base, ID do arquivo no SharePoint, frequência). **Nunca** escreva
o valor do `INTERNAL_SYNC_TOKEN`.

> 🚦 **Checkpoint 6.** Avise o Davi que o `HANDOFF_FLUXO_CONTABIL.md` foi gerado e que ele
> já pode rodar o agent do fluxo apontando pra esse arquivo.

---

## Decisões fechadas (não reabrir)
- Fonte: arquivo `.xlsx` enviado pelo n8n (Graph fica no n8n). Backend não acessa SharePoint.
- Idempotência: `external_id` = hash de conteúdo + contador de ocorrência.
- Categorias: auto-seed normalizado da coluna H; ambíguas/vazias → `para_revisao`.
- Setor → célula por mapa; "Gerais"/desconhecido → `celula_id NULL`.
- Projeto: match por código `NNN.YYYY`; não-código → `NULL`. Nunca cria projeto.
- `contrato_pagamento_id`: sempre NULL aqui.
- Valor sempre positivo; sinal no `tipo`.
- Reusa `INTERNAL_SYNC_TOKEN` e o pool MySQL existentes.
- Arquitetura: n8n fino + lógica em Python testável no backend.
