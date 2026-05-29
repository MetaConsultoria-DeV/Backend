-- Corrige a grafia incorreta das colunas na tabela acompanhamento_projeto
ALTER TABLE acompanhamento_projeto
  RENAME COLUMN primera_resposta TO primeira_resposta,
  RENAME COLUMN dados_iniciais_adicionados TO dados_iniciais_adicionais;
