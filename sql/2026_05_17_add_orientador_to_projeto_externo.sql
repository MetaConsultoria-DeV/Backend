-- Adiciona a fonte de verdade do orientador tecnico no cadastro do projeto.
-- NULL em possui_orientador significa "ainda nao informado".

ALTER TABLE projeto_externo
  ADD COLUMN possui_orientador tinyint(1) DEFAULT NULL
    COMMENT 'NULL = nao informado, 0 = nao possui, 1 = possui'
    AFTER data_inicio,
  ADD COLUMN nome_orientador varchar(150) DEFAULT NULL
    AFTER possui_orientador;

