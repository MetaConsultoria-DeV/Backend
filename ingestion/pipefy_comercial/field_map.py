# field_map.py — IDs estáveis do pipe de Vendas "Sales Pipeline" (734299)
# Gerado por introspecção GraphQL em 2026-06-03. Mapeia por field.id (estável);
# se um campo for renomeado no Pipefy, o id aqui NÃO muda — só o label muda.
#
# REGRA DE ESCOPO: só constam aqui os campos que têm coluna-alvo nas 5 tabelas
# comerciais existentes. Campos sem coluna (anexos, datas de reunião, qualificação
# extra, etc.) são DESCARTADOS de propósito.

PIPE_ID = "734299"
EXTERNAL_SOURCE = "pipefy_comercial"          # leads / oportunidade
EXTERNAL_SOURCE_PHASE = "pipefy_comercial_phase"  # oportunidade_phase_history

# ── leads (start form) ───────────────────────────────────────────────────────
F_NOME      = "nome"            # "Nome"           (contact_name = "Atendente", NÃO é o lead)
F_EMAIL     = "contact_e_mail"  # "Email"
F_TELEFONE  = "contact_phone"   # "Telefone"
F_EMPRESA   = "company_name"    # "Nome da empresa"
F_CARGO     = "profiss_o"       # "Profissão"

# ── oportunidade ─────────────────────────────────────────────────────────────
F_RESPONSAVEIS  = "respons_veis_pela_negocia_o"  # assignee_select (Caixa de Entrada)
F_VALOR_FECHADO = "valor_fechado"                # currency (Pré-Assinatura) — valor canônico

# Coordenação: campos label_select que carregam a etiqueta de coordenação.
# Ordem = prioridade (PC primeiro, depois start form). Fallback: labels do card.
COORD_LABEL_FIELDS = ["how_hot_is_this_opportunity", "engenharia"]

# Nome-da-etiqueta → sigla da tabela `coordenacao` (que só tem TD/GN/OP/CE/DM).
# CP e ND não têm linha correspondente → ficam de fora (coordenacao_id = NULL),
# decisão do Davi (não criar linha nova). Etiquetas de área/termômetro são ignoradas.
COORD_LABEL_TO_SIGLA = {
    "OP": "OP",
    "CE": "CE",
    "GN": "GN",
    "TD": "TD",
    "DM": "DM",
    "Desenvolvimento de Máquinas": "DM",
    "Desenvolvimento de Maquinas": "DM",
}

# ── dim_lead_origem (raw → canonical NULL) — duas fontes, conforme o schema ───
# source_field → field.id
ORIGEM_FIELDS = {
    "start_form": "como_o_cliente_conheceu_a_meta",  # select (start form)
    "ld":         "como_o_lead_conheceu_a_meta",     # radio_vertical (Ligação Diagnóstico)
}
# Prioridade para preencher oportunidade.origem_id: o valor confirmado na LD vence.
ORIGEM_PRIORITY = ["ld", "start_form"]

# ── dim_motivo_perda (raw → canonical NULL) — os campos de motivo por fase ────
# source_field = o próprio field.id. Ordem = prioridade para oportunidade.motivo_perda_id.
MOTIVO_PERDA_FIELDS = [
    "por_qual_motivo_o_projeto_entrou_em_desistidos",                       # Desistidos
    "porque_est_em_postergados",                                           # Postergados
    "por_qual_motivo_o_projeto_vai_para_postergados_parados_desistidos_2",  # Pré-Assinatura
    "por_qual_motivo_o_projeto_vai_para_postergados_parados_desistidos_1",  # Proposta Comercial
    "qual_motivo_o_projeto_vai_para_parados",                               # Reunião Diagnóstico
    "por_qual_motivo_o_projeto_vai_para_desistidos",                        # Ligação Diagnóstico
]

# ── Fases (id → nome) ────────────────────────────────────────────────────────
PHASES = {
    "5170380":   "Caixa de Entrada",
    "5153363":   "Ligação Diagnóstico",
    "7441046":   "Reunião Diagnóstico",
    "334006932": "Validação com Adm-Fin",
    "4984600":   "Proposta Comercial",
    "313949715": "Negociação",
    "4984601":   "Pré-Assinatura de Contrato",
    "313949699": "Retomar contato",
    "8098613":   "Postergados",
    "339067237": "Email Mkt",
    "5172117":   "Desistidos",
    "5153362":   "Recusados",
    "4984603":   "Fechados",
}

# Fase → status_terminal (enum: ativo/fechado/desistido/recusado/postergado).
# Decisão do Davi: "Retomar contato" e "Email Mkt" = postergado.
PHASE_STATUS_TERMINAL = {
    "4984603":   "fechado",     # Fechados
    "5172117":   "desistido",   # Desistidos
    "5153362":   "recusado",    # Recusados
    "8098613":   "postergado",  # Postergados
    "313949699": "postergado",  # Retomar contato
    "339067237": "postergado",  # Email Mkt
}
# Qualquer outra fase → 'ativo'.
STATUS_TERMINAL_DEFAULT = "ativo"
