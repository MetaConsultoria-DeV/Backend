"""transform.py — Flatten de um card Pipefy → dicts por tabela MySQL."""

import re
import unicodedata
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .field_map import (
    EXTERNAL_SOURCE,
    F_NOME_PROJETO, F_NOME_EXTERNO, F_CLIENTE, F_CPF_CNPJ,
    F_VALOR_TOTAL, F_FORMA_PAGAMENTO, F_QTD_PARCELAS,
    F_VENCIMENTO_BASE, F_RECORRENCIA, F_VALOR_VARIAVEL,
    F_ESTIMATIVA_PPP, F_EMAIL_FATURAMENTO, F_TELEFONE,
    PARCELA_FIELD_IDS,
    PHASE_NAME_EM_PAGAMENTO, PHASE_NAME_CONCLUIDO, PHASE_NAME_CANCELADO,
)

logger = logging.getLogger("ingestion.pipefy.transform")

# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_name(text: str) -> str:
    """Lower, sem acento, sem espaço duplo — para matching por nome."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_.lower()).strip()


def _normalize_cpf_cnpj(raw: str) -> Optional[str]:
    """Remove pontuação; retorna None se vazio ou comprimento inválido."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) not in (11, 14):
        return None
    return digits


def _parse_decimal(raw: str) -> Optional[Decimal]:
    if not raw:
        return None
    # Remove "R$", espaços, pontos de milhar; substitui vírgula decimal
    cleaned = re.sub(r"[R$\s]", "", raw).replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _parse_int(raw: str) -> Optional[int]:
    if not raw:
        return None
    try:
        return int(re.sub(r"\D", "", raw))
    except Exception:
        return None


def _parse_datetime(raw: str) -> Optional[datetime]:
    """Tenta vários formatos ISO/Pipefy."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_date(raw: str) -> Optional[date]:
    dt = _parse_datetime(raw)
    return dt.date() if dt else None


def _extract_code(title: str) -> Optional[str]:
    """Extrai código tipo '008.2026' do prefixo do título."""
    if not title:
        return None
    m = re.match(r"^(\d{3}\.\d{4})", title.strip())
    return m.group(1) if m else None


def _build_fields_map(card: dict) -> dict:
    """Retorna {field_id: value} para todos os campos do card."""
    fmap = {}
    for f in card.get("fields", []):
        fid = f["field"]["id"]
        # checklist_vertical devolve array_value; outros devolvem value
        val = f.get("array_value") or f.get("value") or ""
        fmap[fid] = val
    return fmap


def _get_phase_timestamp(card: dict, phase_name: str) -> Optional[datetime]:
    for ph in card.get("phases_history", []):
        if ph["phase"]["name"].strip().lower() == phase_name.lower():
            return _parse_datetime(ph.get("firstTimeIn", ""))
    return None


# ── Funções públicas ──────────────────────────────────────────────────────────

def transform_card(card: dict) -> dict:
    """
    Recebe um node do GraphQL e devolve:
    {
      "forma_pagamento": {...},
      "cliente": {...},
      "projeto_externo": {...},
      "contrato": {...},
      "parcelas": [...],   # lista de dicts contrato_pagamento
      "para_revisao": bool,
      "card_id": str,
    }
    """
    fmap = _build_fields_map(card)
    card_id = card["id"]
    title   = card.get("title", "")
    codigo  = _extract_code(title)

    # ── forma_pagamento ──────────────────────────────────────────────────────
    forma_nome = (fmap.get(F_FORMA_PAGAMENTO) or "").strip() or "Boleto"
    forma_pagamento = {"nome": forma_nome}

    # ── cliente ──────────────────────────────────────────────────────────────
    nome_cliente  = (fmap.get(F_CLIENTE) or "").strip()
    cpf_cnpj_raw  = fmap.get(F_CPF_CNPJ) or ""
    cpf_cnpj      = _normalize_cpf_cnpj(cpf_cnpj_raw)
    email         = (fmap.get(F_EMAIL_FATURAMENTO) or "").strip() or None
    telefone      = (fmap.get(F_TELEFONE) or "").strip() or None

    cliente = {
        "nome":            nome_cliente,
        "nome_normalizado": _normalize_name(nome_cliente),
        "cpf_cnpj":        cpf_cnpj,
        "email":           email,
        "telefone":        telefone,
        "external_source": EXTERNAL_SOURCE,
        "external_id":     card_id,
    }

    # ── projeto_externo ──────────────────────────────────────────────────────
    nome_proj_raw   = (fmap.get(F_NOME_PROJETO) or "").strip()
    # Remove prefixo "008.2026 - " se presente
    nome_proj       = re.sub(r"^\d{3}\.\d{4}\s*[-–]\s*", "", nome_proj_raw).strip()
    descricao_proj  = (fmap.get(F_NOME_EXTERNO) or "").strip() or None

    projeto_externo = {
        "nome":             nome_proj or nome_proj_raw,
        "descricao_projeto": descricao_proj,
        "external_source":  EXTERNAL_SOURCE,
        "external_id":      codigo or card_id,   # código é a chave de matching
    }

    # ── contrato ─────────────────────────────────────────────────────────────
    valor_total      = _parse_decimal(fmap.get(F_VALOR_TOTAL) or "")
    qtd_parcelas     = _parse_int(fmap.get(F_QTD_PARCELAS) or "")
    estimativa_ppp   = _parse_decimal(fmap.get(F_ESTIMATIVA_PPP) or "")
    venc_base_raw    = fmap.get(F_VENCIMENTO_BASE) or ""
    venc_base        = _parse_date(venc_base_raw)
    fase_atual       = (card.get("current_phase") or {}).get("name", "").strip()

    # Número do contrato: extrai do título; fallback FIN-{card_id}
    numero_contrato = codigo if codigo else f"FIN-{card_id}"

    # Timestamps reais de fase
    data_inicio_pagamento = _get_phase_timestamp(card, PHASE_NAME_EM_PAGAMENTO)
    finalizado_em = (
        _get_phase_timestamp(card, PHASE_NAME_CONCLUIDO)
        or _get_phase_timestamp(card, PHASE_NAME_CANCELADO)
    )

    contrato = {
        "numero":               numero_contrato,
        "valor_total":          valor_total,
        "quantidade_parcelas":  qtd_parcelas,
        "estimativa_gastos_ppp": estimativa_ppp,
        "fase_atual":           fase_atual,
        "data_vencimento_base": venc_base,
        "data_inicio_pagamento": data_inicio_pagamento,
        "finalizado_em":        finalizado_em,
        "external_source":      EXTERNAL_SOURCE,
        "external_id":          card_id,
        # FKs preenchidas pelo matching (load.py)
        "cliente_id":           None,
        "projeto_externo_id":   None,
        "forma_pagamento_id":   None,
        "_forma_pagamento_nome": forma_nome,
    }

    # ── parcelas (pivot) ─────────────────────────────────────────────────────
    valor_variavel = (fmap.get(F_VALOR_VARIAVEL) or "").strip().lower()
    para_revisao   = valor_variavel in ("sim", "yes", "s")
    recorrencia    = (fmap.get(F_RECORRENCIA) or "").strip().lower()
    parcelas       = []

    if qtd_parcelas and qtd_parcelas > 0:
        if para_revisao:
            logger.warning("Card %s marcado para revisão (valor variável)", card_id)
        else:
            # Divide igualmente; última parcela absorve resto
            if valor_total:
                unit = (valor_total / qtd_parcelas).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                soma = unit * (qtd_parcelas - 1)
                ultima = valor_total - soma
            else:
                unit = ultima = Decimal("0.00")

            for n in range(1, qtd_parcelas + 1):
                field_id = PARCELA_FIELD_IDS[n - 1] if n <= len(PARCELA_FIELD_IDS) else None
                raw_val  = fmap.get(field_id, "") if field_id else ""

                # checklist_vertical: valor é lista ou string com "Paga"
                if isinstance(raw_val, list):
                    pago = any("paga" in str(v).lower() for v in raw_val)
                else:
                    pago = "paga" in str(raw_val).lower()

                # Data de vencimento
                if venc_base and "mensal" in recorrencia:
                    data_venc = venc_base + timedelta(days=30 * (n - 1))
                else:
                    data_venc = venc_base  # todas na mesma data se não for mensal

                valor_parc = ultima if n == qtd_parcelas else unit

                parcelas.append({
                    "numero_parcela":  n,
                    "total_parcelas":  qtd_parcelas,
                    "valor":           valor_parc,
                    "data_vencimento": data_venc,
                    "data_pagamento":  None,
                    "status":          "pago" if pago else "pendente",
                    "external_source": EXTERNAL_SOURCE,
                    "external_id":     f"{card_id}-p{n}",
                    # FKs preenchidas pelo load.py
                    "contrato_id":          None,
                    "cliente_id":           None,
                    "projeto_externo_id":   None,
                    "forma_pagamento_id":   None,
                })

    return {
        "card_id":        card_id,
        "codigo":         codigo,   # None se o título não tem NNN.YYYY → sync ignora o card
        "forma_pagamento": forma_pagamento,
        "cliente":        cliente,
        "projeto_externo": projeto_externo,
        "contrato":       contrato,
        "parcelas":       parcelas,
        "para_revisao":   para_revisao,
    }
