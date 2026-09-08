-- Gerentes de Projeto: desacoplar o vinculo de gerencia da coordenacao.
--
-- Contexto: membro_projeto.coordenacao_id e NOT NULL, o que obrigava o backend
-- a descobrir uma coordenacao para o gerente antes de gravar. Quem nao tinha
-- coordenacao cadastrada tinha o INSERT silenciosamente pulado, e a API
-- respondia sucesso mesmo assim. Coordenacao descreve por qual area um
-- consultor atua num projeto; gerencia e um cargo a parte e nao tem area.
--
-- Rodar ANTES do deploy do backend novo: o codigo passa a gravar NULL na
-- coluna. Cada bloco tem um SELECT de conferencia antes da escrita.

-- ---------------------------------------------------------------------------
-- 1. Permitir coordenacao nula (apenas relaxa a restricao; retrocompativel com
--    o MetaApp/BDU, que compartilha este banco)
-- ---------------------------------------------------------------------------
ALTER TABLE membro_projeto MODIFY coordenacao_id INT NULL;

-- ---------------------------------------------------------------------------
-- 2. Alinhar cargo institucional: quem gerencia projeto mas nao tem o cargo 31
--    ativo em membro_cargo (Ana Luisa 3, Julia 41, Lucianna 50, Naylan 62)
--
--    membro_cargo e historicizada: a chave unica e (membro_id, cargo_id,
--    data_inicio) e data_inicio e NOT NULL. Um INSERT IGNORE sem data_inicio
--    NAO protege contra duplicata — por isso o NOT EXISTS explicito abaixo,
--    que testa apenas vinculos de cargo em aberto (data_fim IS NULL).
--
--    CURRENT_DATE() aqui e a data de regularizacao do cadastro, nao a data em
--    que a pessoa assumiu a gerencia. Se souber a data real de posse, troque
--    pelo valor correto antes de rodar (as linhas existentes usam 2026-01-01).
-- ---------------------------------------------------------------------------
-- Conferencia:
SELECT DISTINCT m.id, m.nome
FROM membro_projeto mp
JOIN membro m ON m.id = mp.membro_id
WHERE mp.cargo_id = 31
  AND mp.data_saida IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM membro_cargo mc
    WHERE mc.membro_id = mp.membro_id AND mc.cargo_id = 31 AND mc.data_fim IS NULL
  );

INSERT INTO membro_cargo (membro_id, cargo_id, data_inicio)
SELECT DISTINCT mp.membro_id, 31, CURRENT_DATE()
FROM membro_projeto mp
WHERE mp.cargo_id = 31
  AND mp.data_saida IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM membro_cargo mc
    WHERE mc.membro_id = mp.membro_id AND mc.cargo_id = 31 AND mc.data_fim IS NULL
  );

-- ---------------------------------------------------------------------------
-- 3. Zerar a coordenacao das linhas de gerencia (o valor era ruido: gerentes
--    de OP apareciam carimbados como DM, CE ou TD conforme o projeto)
-- ---------------------------------------------------------------------------
-- Conferencia:
SELECT COUNT(*) AS linhas_afetadas
FROM membro_projeto
WHERE cargo_id = 31 AND coordenacao_id IS NOT NULL;

UPDATE membro_projeto SET coordenacao_id = NULL WHERE cargo_id = 31;

-- ---------------------------------------------------------------------------
-- 4. OceanMap (26): a gerente 46 tem duas linhas, uma por coordenacao. Depois
--    do passo 3 elas ficam identicas. Manter a de menor id.
-- ---------------------------------------------------------------------------
-- Conferencia:
SELECT id, membro_id, projeto_externo_id, coordenacao_id, data_saida
FROM membro_projeto
WHERE projeto_externo_id = 26 AND cargo_id = 31;

DELETE FROM membro_projeto
WHERE projeto_externo_id = 26
  AND cargo_id = 31
  AND id NOT IN (
    SELECT menor FROM (
      SELECT MIN(id) AS menor FROM membro_projeto
      WHERE projeto_externo_id = 26 AND cargo_id = 31
    ) AS t
  );

-- ---------------------------------------------------------------------------
-- 5. Valida Bruninho (29): dois gerentes ativos ao mesmo tempo. Julia Peixoto
--    Dib (41) fica. Ana Luisa (3) sai, mas segue elegivel pelo cargo
--    institucional inserido no passo 2.
-- ---------------------------------------------------------------------------
-- Conferencia:
SELECT mp.id, m.nome, mp.data_saida
FROM membro_projeto mp
JOIN membro m ON m.id = mp.membro_id
WHERE mp.projeto_externo_id = 29 AND mp.cargo_id = 31;

UPDATE membro_projeto
SET data_saida = CURRENT_DATE()
WHERE projeto_externo_id = 29
  AND cargo_id = 31
  AND membro_id = 3
  AND data_saida IS NULL;

-- ---------------------------------------------------------------------------
-- 6. TEMPLATE — virada de semestre. Nao executar como esta.
--    Trocar <PROJETO_ID>, <MEMBRO_ID_ANTIGO>, <MEMBRO_ID_NOVO> e as datas.
-- ---------------------------------------------------------------------------
-- Encerra o gerente atual:
-- UPDATE membro_projeto
-- SET data_saida = '2026-08-01'
-- WHERE projeto_externo_id = <PROJETO_ID>
--   AND cargo_id = 31
--   AND membro_id = <MEMBRO_ID_ANTIGO>
--   AND data_saida IS NULL;
--
-- Encerra o cargo institucional de quem deixou a gerencia, se for o caso:
-- UPDATE membro_cargo
-- SET data_fim = '2026-08-01'
-- WHERE membro_id = <MEMBRO_ID_ANTIGO> AND cargo_id = 31 AND data_fim IS NULL;
--
-- Garante o cargo institucional do novo gerente (basta isso para ele passar a
-- aparecer no dropdown de /api/gerentes/elegiveis):
-- INSERT INTO membro_cargo (membro_id, cargo_id, data_inicio)
-- VALUES (<MEMBRO_ID_NOVO>, 31, '2026-08-01');
--
-- Abre o vinculo novo (coordenacao_id fica NULL de proposito):
-- INSERT INTO membro_projeto
--   (membro_id, projeto_externo_id, coordenacao_id, cargo_id, data_entrada)
-- VALUES (<MEMBRO_ID_NOVO>, <PROJETO_ID>, NULL, 31, '2026-08-01');
