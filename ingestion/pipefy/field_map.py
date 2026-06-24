"""Configuration module containing field mappings and phase definitions for Pipefy Financeiro.

Maps the API field identifiers (which are stable even if fields are renamed on the Pipefy UI)
and phase identifiers to friendly Python constants. This includes primary project form fields,
the 12 sequential installment field IDs, and phase status IDs/names.
"""

# The unique identifier for the Finance pipe in Pipefy
PIPE_ID = "306946459"

# External source name used for database records mapping
EXTERNAL_SOURCE = "pipefy_financeiro"

# --- Main form fields mapping ---
F_NOME_PROJETO          = "nome_do_projeto"                            # Project internal name
F_NOME_EXTERNO          = "nome_externo_do_projeto"                    # Project external/commercial name
F_CLIENTE               = "cliente"                                    # Client name
F_CPF_CNPJ              = "copy_of_cliente"                            # Client CPF/CNPJ identifier
F_VALOR_TOTAL           = "valor_total_do_contrato"                    # Contract total financial value
F_FORMA_PAGAMENTO       = "forma_de_pagamento"                        # Payment method
F_QTD_PARCELAS          = "quantidade_de_parcelas"                    # Number of installments
F_VENCIMENTO_BASE       = "data_de_vencimento_das_parcelas_fixo"       # Fixed reference day for installment due dates
F_RECORRENCIA           = "recorr_ncia"                                # Billing recurrence interval (e.g. Monthly)
F_VALOR_VARIAVEL        = "possui_valor_vari_vel_ou_extra"             # Flag for variable or extra value
F_ESTIMATIVA_PPP        = "estimativa_de_gastos_ppp"                   # Estimated cost for PPP cell
F_EMAIL_FATURAMENTO     = "e_mail_para_envio_de_faturamento_nf"        # Invoicing billing email
F_TELEFONE              = "telefone_de_contato_financeiro_do_cliente"  # Client financial contact phone number

# --- Installment Field IDs (Fase: "Em pagamento") ---
# Array of field IDs for installments from index 1 to 12.
# When fields are copied/created in Pipefy, they dynamically receive 'copy_of' prefixes.
PARCELA_FIELD_IDS = [
    "1_parcela",                                                                          # Installment 1
    "copy_of_1_parcela",                                                                  # Installment 2
    "copy_of_copy_of_1_parcela",                                                          # Installment 3
    "copy_of_copy_of_copy_of_1_parcela",                                                  # Installment 4
    "copy_of_copy_of_copy_of_copy_of_1_parcela",                                          # Installment 5
    "copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                                  # Installment 6
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                          # Installment 7
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",                  # Installment 8
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",          # Installment 9
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",  # Installment 10
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela",        # Installment 11
    "copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_copy_of_1_parcela", # Installment 12
]

# --- Phase IDs (used for matching transitions and phase timestamps) ---
PHASE_ID_EM_PAGAMENTO = "341898939"
PHASE_ID_CONCLUIDO    = "341898969"
PHASE_ID_CANCELADO    = "341898970"

# --- Phase Names (string tags matching the API / UI names) ---
PHASE_NAME_EM_PAGAMENTO = "Em pagamento"
PHASE_NAME_CONCLUIDO    = "Concluido"
PHASE_NAME_CANCELADO    = "Cancelado"

