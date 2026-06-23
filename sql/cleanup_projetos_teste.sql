-- Limpeza de projetos de teste inseridos por engano na aba Contratos & Financeiro.
-- Espelha a ordem de exclusao de _delete_projeto_tx (backend/main.py), respeitando as FKs RESTRICT.
-- Esta versão usa subqueries diretas e desativa temporariamente o Safe Updates para rodar no Workbench.
--

-- Desativa o modo Safe Updates na sessão atual
SET SQL_SAFE_UPDATES = 0;

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

-- 1.1) Desvincula transações das parcelas associadas aos contratos dos projetos
UPDATE transacao SET contrato_pagamento_id = NULL
WHERE contrato_pagamento_id IN (
  SELECT id FROM (
    SELECT id FROM contrato_pagamento 
    WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'))
       OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto')) OR numero LIKE 'CONTRATO-TEMP-%')
  ) tmp
);

-- 1.2) Desvincula transações diretas dos projetos
UPDATE transacao SET projeto_externo_id = NULL
WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'));

-- 1.3) Deleta acompanhamentos
DELETE FROM acompanhamento_projeto
WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'))
   OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto')) OR numero LIKE 'CONTRATO-TEMP-%');

-- 1.4) Deleta parcelas de pagamento
DELETE FROM contrato_pagamento
WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'))
   OR contrato_id IN (SELECT id FROM contrato WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto')) OR numero LIKE 'CONTRATO-TEMP-%');

-- 1.5) Deleta vínculos de membros e serviços dos projetos
DELETE FROM membro_projeto WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'));
DELETE FROM projeto_servico WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'));

-- 1.6) Deleta os Contratos
DELETE FROM contrato 
WHERE projeto_externo_id IN (SELECT id FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto'))
   OR numero LIKE 'CONTRATO-TEMP-%';

-- 1.7) Deleta os Projetos
DELETE FROM projeto_externo WHERE nome IN ('Protege Catódica', 'Verifica Telhadinho', 'Valida Bruninho', 'Projeta Pousadona', 'Arquiteta Odonto');

-- Se tudo bateu e rodou com sucesso:
COMMIT;
-- Se algo estranho, NAO de COMMIT; rode:  ROLLBACK;

-- Reativa o modo Safe Updates na sessão atual por segurança
SET SQL_SAFE_UPDATES = 1;
