-- migration_pipefy_financeiro.sql
-- Objetivo: garantir idempotência do upsert de forma_pagamento na ingestão do
-- Pipefy Financeiro. O load.upsert_forma_pagamento usa
-- "INSERT ... ON DUPLICATE KEY UPDATE nome = VALUES(nome)", que SÓ deduplica se
-- existir uma UNIQUE KEY em forma_pagamento(nome). Hoje a tabela só tem PK(id),
-- então cada sync insere uma forma duplicada. Esta migration adiciona a unique.
--
-- As demais âncoras de idempotência já existem no schema e NÃO são recriadas:
--   cliente            -> uq_cliente_cpf_cnpj, uk_cliente_external(external_source,external_id)
--   contrato           -> uq_contrato_numero, uq_contrato_projeto, uk_contrato_external
--   contrato_pagamento -> uk_contrato_pagamento_external(external_source,external_id)
--
-- COMO APLICAR:
--   1) Rode o PRÉ-CHECK abaixo. Se vier alguma linha, há nomes duplicados —
--      consolide antes (a ALTER vai falhar com nomes repetidos).
--   2) Rode o bloco de ALTER (idempotente: não falha se a unique já existir).

-- ── PRÉ-CHECK: precisa retornar VAZIO antes de aplicar a unique ───────────────
SELECT nome, COUNT(*) AS qtd
FROM forma_pagamento
GROUP BY nome
HAVING qtd > 1;

-- ── ALTER idempotente: adiciona uk_forma_pagamento_nome só se ainda não existir ─
SET @exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name   = 'forma_pagamento'
    AND index_name   = 'uk_forma_pagamento_nome'
);
SET @ddl := IF(@exists = 0,
  'ALTER TABLE forma_pagamento ADD UNIQUE KEY uk_forma_pagamento_nome (nome)',
  'SELECT "uk_forma_pagamento_nome ja existe" AS info'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
