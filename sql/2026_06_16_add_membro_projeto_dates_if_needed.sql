-- Migração para garantir que as colunas data_entrada e data_saida existam na tabela membro_projeto.
-- Nota: Estas colunas já estão no schema do PAPE, mas esta migration serve de asserção.

-- Executando de forma compatível com MySQL sem DDL direto sob condições
DELIMITER //

CREATE PROCEDURE IF NOT EXISTS CheckAndAddDates()
BEGIN
    -- data_entrada
    IF NOT EXISTS (
        SELECT * FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
          AND TABLE_NAME = 'membro_projeto' 
          AND COLUMN_NAME = 'data_entrada'
    ) THEN
        ALTER TABLE `membro_projeto` ADD COLUMN `data_entrada` DATE NULL DEFAULT NULL;
    END IF;

    -- data_saida
    IF NOT EXISTS (
        SELECT * FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
          AND TABLE_NAME = 'membro_projeto' 
          AND COLUMN_NAME = 'data_saida'
    ) THEN
        ALTER TABLE `membro_projeto` ADD COLUMN `data_saida` DATE NULL DEFAULT NULL;
    END IF;
END //

DELIMITER ;

CALL CheckAndAddDates();
DROP PROCEDURE IF EXISTS CheckAndAddDates;
