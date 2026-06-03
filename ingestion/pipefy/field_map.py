# field_map.py — IDs estáveis do pipe Financeiro (306946459)
# Gerado por introspecção em 2026-06-01. NÃO alterar manualmente;
# se um campo for renomeado no Pipefy, o id aqui NÃO muda — só o label muda.

PIPE_ID = "306946459"
EXTERNAL_SOURCE = "pipefy_financeiro"

# ── Campos do formulário principal ──────────────────────────────────────────
F_NOME_PROJETO          = "nome_do_projeto"
F_NOME_EXTERNO          = "nome_externo_do_projeto"
F_CLIENTE               = "cliente"
F_CPF_CNPJ              = "copy_of_cliente"
F_VALOR_TOTAL           = "valor_total_do_contrato"
F_FORMA_PAGAMENTO       = "forma_de_pagamento"
F_QTD_PARCELAS          = "quantidade_de_parcelas"
F_VENCIMENTO_BASE       = "data_de_vencimento_das_parcelas_fixo"
F_RECORRENCIA           = "recorr_ncia"
F_VALOR_VARIAVEL        = "possui_valor_vari_vel_ou_extra"
F_ESTIMATIVA_PPP        = "estimativa_de_gastos_ppp"
F_EMAIL_FATURAMENTO     = "e_mail_para_envio_de_faturamento_nf"
F_TELEFONE              = "telefone_de_contato_financeiro_do_cliente"

# ── Campos de parcelas (fase "Em pagamento") — ordem 1..12 ──────────────────
PARCELA_FIELD_IDS = [
    "1_parcela",                                                                          # 1
    "copy_of_1_parcela",                                                                  # 2
    "copy_of_copy_of_1_parcela",                                                          # 3
    "copy_of_copy_of_copy_of_1_parcela",                                                  # 4
    "copy_of_copy_of_copy_of_copy_of_1_parcela",                                          # 5
    "copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                                  # 6
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                          # 7
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                  # 8
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",          # 9
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",  # 10
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",        # 11
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela", # 12
]

# ── IDs de fases (para timestamps via phases_history) ───────────────────────
PHASE_ID_EM_PAGAMENTO = "341898939"
PHASE_ID_CONCLUIDO    = "341898969"
PHASE_ID_CANCELADO    = "341898970"

PHASE_NAME_EM_PAGAMENTO = "Em pagamento"
PHASE_NAME_CONCLUIDO    = "Concluido"
PHASE_NAME_CANCELADO    = "Cancelado"
