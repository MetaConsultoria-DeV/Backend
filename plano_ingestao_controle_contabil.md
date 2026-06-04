# Plano de Ingestão — Controle Contábil (planilha SharePoint → MySQL)

> **Fonte de verdade** do mapeamento campo→tabela, regras de transformação e decisões
> fechadas. Os dois agents (`agent_backend_ingestao_contabil.md` e
> `agent_fluxo_n8n_contabil.md`) implementam a partir daqui; não reinventam regra.
>
> Análogo aos planos do Pipefy, mas com **uma diferença estrutural**: a fonte não é uma
> API GraphQL, é um **arquivo Excel hospedado no SharePoint/Excel Online**, atualizado à
> mão pelas analistas financeiras. Quem baixa o arquivo é o **n8n** (já tem a credencial
> Microsoft Graph); o backend recebe o `.xlsx` por upload e faz o parsing.

---

## 0. Contexto e objetivo

A planilha **"Controle Contábil.xlsm"** é o caixa livre da empresa. As analistas
lançam toda entrada/saída de todas as contas. Hoje as tabelas `transacao` e
`categoria_transacao` do banco estão **vazias** — toda essa realidade financeira vive só
no Excel. Objetivo: manter `transacao` (e `categoria_transacao`) sincronizadas com a
planilha, da mesma forma idempotente que os syncs de Pipefy.

O schema **já foi desenhado para isso**: `transacao` tem
`external_source DEFAULT 'sharepoint_caixa'` e o comentário "Transacoes da planilha
SharePoint (caixa livre)". Não criamos tabela nova.

---

## 1. Anatomia da planilha (o que o parser precisa saber)

Arquivo: **1 aba** (`Controle Contábil`), ~716 linhas, ~701 transações reais
(período 2024-01 → 2026-06). O layout tem três zonas; **só a do meio interessa**:

| Zona | Colunas (letra) | O que é | Uso |
|---|---|---|---|
| Painel esquerdo | A–B | "VISÃO GERAL / RECEITAS / Projetos…" (resumo) | **ignorar** |
| **REGISTRO DE TRANSAÇÕES** | **D–K** | a tabela de lançamentos | **esta é a fonte** |
| Painel direito | R–V | categorias por setor + orçamento/dívidas | hint opcional (ver §4) |

### Cabeçalho e início dos dados
O cabeçalho **"Data | Conta | Entrada/Saída | Setor | Categoria | Nº do Projeto… | Valor
| Observações"** aparece **duas vezes** na planilha. A tabela real é a **segunda**
ocorrência (a que tem, à direita, as colunas auxiliares `mm/aaaa | Real | Acumulado`).
Hoje ela está na linha 10 (1-based), dados a partir da linha 11.

> **Não hardcodar o número da linha.** O parser localiza a linha de cabeçalho
> procurando, nas colunas D–K, a sequência de rótulos `Data`/`Conta`/`Setor`/`Valor`
> (normalizados), e lê os dados a partir da linha seguinte até o primeiro bloco
> totalmente vazio. As analistas inserem linhas; ancorar por rótulo, não por índice.

### Colunas da tabela (D–K)

| Col | Rótulo | Exemplo | Vai para |
|---|---|---|---|
| D | Data | `2026-06-01` | `transacao.data` |
| E | Conta | `Cora` | `transacao.conta_id` (lookup) |
| F | Entrada/Saída | `Saída` | `transacao.tipo` |
| G | Setor | `Operações` | `transacao.celula_id` (lookup) |
| H | Categoria | `Clicksign` | `transacao.categoria_id` (lookup/seed) |
| I | Nº do Projeto / Gasto Extra / Dívida | `010.2026` | `transacao.projeto_externo_id` (match) |
| J | Valor | `229.62` | `transacao.valor` |
| K | Observações | `Clicksign - Bryan` | usado no hash de `external_id` |

---

## 2. Mapeamento campo → `transacao`

| Coluna `transacao` | Origem | Regra |
|---|---|---|
| `data` (date, NOT NULL) | col D | data da célula; linha sem data válida → **descartar** (não é transação) |
| `conta_id` (NOT NULL) | col E | lookup em `conta_bancaria.nome` (Cora=1, Asaas=2, Santander=3, Lojinha de GP=4). Sem conta → `para_revisao`, não grava |
| `tipo` enum(entrada,saida) | col F | normaliza: "Saída"→`saida`, "Entrada"→`entrada` |
| `categoria_id` (nullable) | col H | lookup em `categoria_transacao` (ver §4). Vazia/ambígua → `NULL` + `para_revisao` |
| `celula_id` (nullable) | col G | normaliza+mapeia setor→célula (ver §3). "Gerais"→`NULL`; desconhecido→`NULL`+revisão |
| `valor` decimal(15,2) "Sempre positivo" | col J | `abs(valor)`; o sinal vive no `tipo` |
| `projeto_externo_id` (nullable) | col I | se casar `NNN.YYYY` → match em `projeto_externo.codigo`; senão `NULL` |
| `contrato_pagamento_id` (nullable) | — | **fora desta automação** (é o cross-link do sync financeiro do Pipefy). Sempre `NULL` aqui |
| `external_source` (NOT NULL) | fixo | `'sharepoint_caixa'` |
| `external_id` (NOT NULL) | derivado | hash de conteúdo + contador (ver §5) |

### `projeto_externo_id` — matching por código
A coluna I mistura códigos de projeto (`010.2026`, `011.2025` — padrão **`NNN.YYYY`**, o
mesmo do Pipefy) com rótulos que **não são projeto** (`ImpulseUp`, `Reajuste de Saldo`,
`Transações entre Contas`, `MetaStore`, vazio…). Regra: extrair `NNN.YYYY`; se casar com
`projeto_externo.codigo`, vincula; **senão `projeto_externo_id = NULL`** (não é erro,
é gasto/ganho extra ou movimento interno). **Nunca criar `projeto_externo`** a partir
daqui — projetos vêm do Pipefy.

---

## 3. Normalização de Setor → `celula`

Os setores vêm sujos (espaços à direita, variações). Normalizar (`strip`, colapsar
espaços, `casefold`) e mapear:

| Setor na planilha (normalizado) | `celula` | Código |
|---|---|---|
| presidência | Presidência | PRES |
| projetos | Projetos | PROJ |
| operações | Operações | OPS |
| gestão de pessoas | Gestão de Pessoas | GP |
| marketing | Marketing e Vendas | MKTV |
| área comercial | Marketing e Vendas | MKTV (🚦 confirmar) |
| gerais | — | `celula_id = NULL` (movimento interno/geral) |
| *qualquer outro* | — | `NULL` + `para_revisao` |

---

## 4. `categoria_transacao` — auto-seed normalizado + revisão

**Decisão:** semear `categoria_transacao` a partir dos valores distintos da coluna H,
normalizados. **Carregar categorias ANTES das transações** (FK).

Regras:
1. Normalizar nome: `strip`, colapsar espaços internos, casar **case-insensitive**.
   `'Camisas Polo '` e `'Camisas Polo'` → **uma** categoria. Guardar o nome na forma
   mais "limpa" encontrada (Title/como aparece sem espaços sobrando).
2. `tipo` (enum entrada/saida/ambos): inferir pelas transações onde a categoria aparece
   — só entradas → `entrada`; só saídas → `saida`; ambas → `ambos`.
3. `celula_id`: o setor predominante da categoria; se misto/indefinido → `NULL`.
4. Categoria **vazia** (102 linhas) → transação fica com `categoria_id = NULL` e a linha
   entra em `para_revisao`.
5. Variações suspeitas de typo (ex.: `Materias de Apoio` vs `Materiais de Apoio`,
   `StakeHolders` vs `Stakeholders`) → criar como estão, mas **listar em `para_revisao`**
   pra Davi fundir manualmente depois. Não tentar adivinhar fusão automática.
6. **Hint opcional:** o painel direito (cols R–V) lista categorias por setor com
   orçamento. O agent **pode** lê-lo para reforçar a inferência de `celula_id`/`tipo`,
   mas a fonte primária do seed é a coluna H (decisão fechada). Não bloquear nele.

`ativo = 1` por padrão.

---

## 5. Idempotência — `external_id` (hash de conteúdo + contador)

A planilha **não tem coluna de ID**. `transacao` exige
`UNIQUE (external_source, external_id)`. Estratégia fechada:

```
base   = f"{data_iso}|{conta}|{tipo}|{setor_norm}|{categoria_norm}|{valor:.2f}|{obs_norm}"
h      = sha1(base).hexdigest()[:16]
extid  = f"{h}-{ocorrencia}"        # ocorrencia = 1,2,3… por hash idêntico, na ordem da planilha
```

- **Estável a reordenação** de linhas (não depende do número da linha).
- O **contador** desambígua duplicatas legítimas (duas transações idênticas no mesmo dia
  contam como `-1` e `-2`). Conta na **ordem de leitura da planilha** (determinístico
  entre execuções enquanto a ordem relativa dos iguais não muda).
- **Limitação conhecida (documentar pro Davi):** se uma analista **corrige** uma linha já
  ingerida (ex.: conserta um typo na observação), o hash muda → vira um registro **novo**;
  o antigo continua no banco órfão. Mesma família do problema de
  *contrato identidade instável*. Mitigação operacional: o resultado do sync reporta
  `inseridos` alto inesperado como sinal de edição retroativa; limpeza de órfãos é manual.
  (Se isso incomodar no uso real, a saída é a "coluna de ID na planilha" — trocar a
  estratégia sem mudar o resto.)

Todo INSERT é `ON DUPLICATE KEY UPDATE` na unique `(external_source, external_id)`.

---

## 6. Ordem de carga (respeitando FKs)

1. `categoria_transacao` (upsert por `nome`) — precisa existir antes da transação.
2. `transacao` (upsert por `external_source, external_id`), resolvendo
   `conta_id` / `celula_id` / `categoria_id` / `projeto_externo_id` por lookup.

`conta_bancaria` e `celula` **já estão populadas** (referência) — apenas lookup, nunca
inserir. `projeto_externo` vem do Pipefy — apenas lookup.

---

## 7. Endpoint de gatilho

- `POST /internal/sync/controle-contabil`
- Auth: header `X-Internal-Token == INTERNAL_SYNC_TOKEN` (401 se faltar/errar).
- **Corpo: o arquivo `.xlsx`** (multipart `file`), enviado pelo n8n.
- `?dry_run=true` → roda tudo e **não grava** (loga o que faria).
- Resposta JSON (mesma forma dos outros syncs):
  `{ "lidos", "ignorados", "inseridos", "atualizados", "categorias_criadas", "para_revisao": [...], "erros": [...] }`.

---

## 8. Decisões fechadas (não reabrir)

- **Transporte:** o **n8n** baixa o `.xlsx` (credencial Microsoft Graph que já existe) e
  faz POST do arquivo pro backend. Graph **só no n8n** — não criar app registration no
  backend.
- **Idempotência:** hash de conteúdo + contador de ocorrência (§5).
- **Categorias:** auto-seed normalizado a partir da coluna H; ambíguas/vazias → revisão (§4).
- **Setor:** normaliza e mapeia para `celula`; "Gerais" e desconhecidos → `celula_id NULL` (§3).
- **Projeto:** match por código `NNN.YYYY` em `projeto_externo`; não-código → `NULL`. Nunca cria projeto.
- **`contrato_pagamento_id`:** fora desta automação (sempre NULL).
- **Valor:** sempre positivo (`abs`); sinal no `tipo`.
- **Arquitetura:** n8n fino + lógica em Python testável no backend (igual Pipefy).
- **Fonte de verdade do contrato entre agents:** `HANDOFF_FLUXO_CONTABIL.md`.
