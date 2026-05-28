-- Migration para adicionar coluna de descrição do projeto em projeto_externo
ALTER TABLE `projeto_externo` ADD COLUMN `descricao_projeto` VARCHAR(500) DEFAULT NULL;
