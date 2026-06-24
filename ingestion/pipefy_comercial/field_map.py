"""Configuration module containing field mappings and phase definitions for Pipefy Comercial.

Maps the API field identifiers and phase identifiers for the Sales Pipeline. Defines scope
boundaries (discarding fields without database column mappings), lead sources, loss reasons,
and terminal status mappings (e.g. converting 'Desistidos' or 'Postergados' into terminal statuses).
"""

# The unique identifier for the Sales Pipe in Pipefy
PIPE_ID = "734299"

# External source names used for database tracking
EXTERNAL_SOURCE = "pipefy_comercial"          # Primary source for leads/opportunities
EXTERNAL_SOURCE_PHASE = "pipefy_comercial_phase"  # Source for opportunity_phase_history

# --- Leads (start form fields) ---
F_NOME      = "nome"            # Contact name/lead name
F_EMAIL     = "contact_e_mail"  # Contact email address
F_TELEFONE  = "contact_phone"   # Contact phone number
F_EMPRESA   = "company_name"    # Client company name
F_CARGO     = "profiss_o"       # Client profession / job title

# --- Opportunity ---
F_RESPONSAVEIS  = "respons_veis_pela_negocia_o"  # Negotiators assignee select field
F_VALOR_FECHADO = "valor_fechado"                # Canonical closed contract currency value

# --- Coordination Label Fields ---
# Priorities for resolving coordination cell labels. Fallback is the card label tag.
COORD_LABEL_FIELDS = ["how_hot_is_this_opportunity", "engenharia"]

# Label name mapping to coordination cell abbreviations in the `coordenacao` table.
# Labels not in this dictionary map to NULL.
COORD_LABEL_TO_SIGLA = {
    "OP": "OP",
    "CE": "CE",
    "GN": "GN",
    "TD": "TD",
    "DM": "DM",
    "Desenvolvimento de Máquinas": "DM",
    "Desenvolvimento de Maquinas": "DM",
}

# --- Lead Origins mapping (dim_lead_origem) ---
# Maps different custom fields in different pipeline phases that capture how the client heard about Meta.
ORIGEM_FIELDS = {
    "start_form": "como_o_cliente_conheceu_a_meta",  # Source selection in the start form
    "ld":         "como_o_lead_conheceu_a_meta",     # Source selection in Ligação Diagnóstico (LD)
}
# Priority list: LD selection is more concrete and overrides start form values.
ORIGEM_PRIORITY = ["ld", "start_form"]

# --- Lead Loss Reasons (dim_motivo_perda) ---
# List of field IDs where loss reasons are captured across different stages.
# Priority matches order (from earliest/most specific loss field down to general ones).
MOTIVO_PERDA_FIELDS = [
    "por_qual_motivo_o_projeto_entrou_em_desistidos",                       # Phase: Desistidos
    "porque_est_em_postergados",                                           # Phase: Postergados
    "por_qual_motivo_o_projeto_vai_para_postergados_parados_desistidos_2",  # Phase: Pré-Assinatura
    "por_qual_motivo_o_projeto_vai_para_postergados_parados_desistidos_1",  # Phase: Proposta Comercial
    "qual_motivo_o_projeto_vai_para_parados",                               # Phase: Reunião Diagnóstico
    "por_qual_motivo_o_projeto_vai_para_desistidos",                        # Phase: Ligação Diagnóstico
]

# --- Sales pipeline phases (ID to Stage Name mapping) ---
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
# --- Stage Terminal Status mapping ---
# Maps specific terminal phase IDs to active/inactive categories.
# Phases not listed here default to 'ativo'.
PHASE_STATUS_TERMINAL = {
    "4984603":   "fechado",     # Finished/won
    "5172117":   "desistido",   # Given up
    "5153362":   "recusado",    # Rejected
    "8098613":   "postergado",  # Postponed
    "313949699": "postergado",  # Retomar contato
    "339067237": "postergado",  # Email Mkt
}

# Default status for any non-terminal/intermediate pipeline stage
STATUS_TERMINAL_DEFAULT = "ativo"
