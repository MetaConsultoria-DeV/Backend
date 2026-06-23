-- Limpeza de projetos de teste inseridos por engano na aba Contratos & Financeiro.
-- Espelha a ordem de exclusao de _delete_projeto_tx (backend/main.py), respeitando as FKs RESTRICT.
-- Esta versão é DINÂMICA e descobre os IDs dos registros automaticamente na VPS ou local.
--

-- ============================================================
-- 0) PREVIEW: Visualize os registros que serão removidos
-- ============================================================
SELECT pe.id AS projeto_id, pe.nome AS projeto,
       c.id AS contrato_id, c.numero, cli.nome AS cliente, c.valor_total
FROM projeto_externo pe
LEFT JOIN contrato c   ON c.projeto_externo_id = pe.id
LEFT JOIN cliente cli  ON cli.id = c.cliente_id
WHERE pe.nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto')
   OR c.numero LIKE 'CONTRATO-TEMP-%';

-- ============================================================
-- 1) EXCLUSAO (transacional). Confira os "rows affected" antes do COMMIT.
-- ============================================================
START TRANSACTION;

-- 1.1) Guarda os IDs dos projetos que queremos remover em uma tabela temporária
CREATE TEMPORARY TABLE IF NOT EXISTS projetos_a_remover AS
SELECT id FROM projeto_externo 
WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto');

-- 1.2) Guarda os IDs dos contratos que queremos remover em outra tabela temporária
CREATE TEMPORARY TABLE IF NOT EXISTS contratos_a_remover AS
SELECT id FROM contrato 
WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover)
   OR numero LIKE 'CONTRATO-TEMP-%';

-- 1.3) Desvincula transações das parcelas e projetos
UPDATE transacao SET contrato_pagamento_id = NULL
WHERE contrato_pagamento_id IN (SELECT id FROM contrato_pagamento WHERE contrato_id IN (SELECT id FROM contratos_a_remover));

UPDATE transacao SET projeto_externo_id = NULL
WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover);

-- 1.4) Deleta acompanhamentos
DELETE FROM acompanhamento_projeto
WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover)
   OR contrato_id IN (SELECT id FROM contratos_a_remover);

-- 1.5) Deleta parcelas de pagamento
DELETE FROM contrato_pagamento
WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover)
   OR contrato_id IN (SELECT id FROM contratos_a_remover);

-- 1.6) Deleta vínculos de membros e serviços dos projetos
DELETE FROM membro_projeto WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover);
DELETE FROM projeto_servico WHERE projeto_externo_id IN (SELECT id FROM projetos_a_remover);

-- 1.7) Deleta os Contratos
DELETE FROM contrato WHERE id IN (SELECT id FROM contratos_a_remover);

-- 1.8) Deleta os Projetos
DELETE FROM projeto_externo WHERE id IN (SELECT id FROM projetos_a_remover);

-- 1.9) Limpa as tabelas temporárias auxiliares
DROP TEMPORARY TABLE projetos_a_remover;
DROP TEMPORARY TABLE contratos_a_remover;

-- Se tudo bateu e rodou com sucesso:
COMMIT;
-- Se algo estranho, NAO de COMMIT; rode:  ROLLBACK;
