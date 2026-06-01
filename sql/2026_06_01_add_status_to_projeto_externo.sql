ALTER TABLE projeto_externo 
ADD COLUMN status ENUM('ativo', 'finalizado', 'pausado') NOT NULL DEFAULT 'ativo';

-- Migrar status atual
UPDATE projeto_externo 
SET status = 'pausado' 
WHERE LOWER(descricao) LIKE '%pausado%';

UPDATE projeto_externo pe
LEFT JOIN contrato c ON c.projeto_externo_id = pe.id
LEFT JOIN (
    SELECT ap1.projeto_externo_id, ap1.status_cronograma
    FROM acompanhamento_projeto ap1
    WHERE NOT EXISTS (
        SELECT 1 FROM acompanhamento_projeto ap2
        WHERE ap2.projeto_externo_id = ap1.projeto_externo_id
          AND (ap2.data_resposta > ap1.data_resposta OR (ap2.data_resposta = ap1.data_resposta AND ap2.id > ap1.id))
    )
) ap ON ap.projeto_externo_id = pe.id
SET pe.status = 'finalizado'
WHERE (c.finalizado_em IS NOT NULL OR c.fase_atual IN ('Concluido', 'Cancelado') OR ap.status_cronograma IN ('Concluido', 'Concluído'))
  AND (c.numero IS NULL OR c.numero NOT LIKE 'CONTRATO-TEMP%');
