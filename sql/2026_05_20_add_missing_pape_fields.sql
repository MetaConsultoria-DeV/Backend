-- Adiciona os campos faltantes na tabela de acompanhamento de projetos
ALTER TABLE acompanhamento_projeto
ADD COLUMN primeira_resposta TINYINT(1) DEFAULT 0,
ADD COLUMN cliente_percebeu_valor INT NULL,
ADD COLUMN pct_marcos_prazo VARCHAR(20) NULL,
ADD COLUMN variacao_escopo INT NULL,
ADD COLUMN impacto_cliente VARCHAR(50) NULL,
ADD COLUMN abertura_cliente INT NULL,
ADD COLUMN satisfacao_cliente INT NULL,
ADD COLUMN suficiencia_orcamento_nota INT NULL,
ADD COLUMN dados_iniciais_adicionais JSON NULL;

-- Adiciona os campos faltantes na avaliação do orientador
ALTER TABLE acomp_orientador
ADD COLUMN efetividade_orientador INT NULL,
ADD COLUMN disponibilidade_orientador INT NULL;
