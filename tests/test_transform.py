"""Testes unitários do transform.py — não precisam de banco nem de Pipefy."""

import pytest
from decimal import Decimal
from ingestion.pipefy.transform import transform_card, _normalize_cpf_cnpj, _extract_code


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_field(field_id: str, value: str = "", array_value=None) -> dict:
    return {
        "name": field_id,
        "value": value,
        "array_value": array_value,
        "field": {"id": field_id, "type": "short_text"},
    }


def _base_card(card_id="123456789", title="008.2026 - Legaliza Coelhinha",
               fase="Em pagamento", qtd_parcelas="2", valor="4000") -> dict:
    return {
        "id": card_id,
        "title": title,
        "current_phase": {"name": fase},
        "createdAt": "2026-01-01T00:00:00Z",
        "finished_at": None,
        "fields": [
            _make_field("cliente", "Jeane Coelho de Mello"),
            _make_field("copy_of_cliente", ""),
            _make_field("valor_total_do_contrato", valor),
            _make_field("forma_de_pagamento", "Boleto"),
            _make_field("quantidade_de_parcelas", qtd_parcelas),
            _make_field("data_de_vencimento_das_parcelas_fixo", "2026-03-01T00:00:00Z"),
            _make_field("recorr_ncia", "Mensal (30 dias)"),
            _make_field("possui_valor_vari_vel_ou_extra", "Não"),
            _make_field("nome_do_projeto", "008.2026 - Legaliza Coelhinha"),
            _make_field("estimativa_de_gastos_ppp", ""),
            # Parcela 1 paga, parcela 2 pendente
            _make_field("1_parcela", "", array_value=["1° Parcela Paga"]),
            _make_field("copy_of_1_parcela", "", array_value=[]),
        ],
        "phases_history": [
            {"phase": {"id": "341898939", "name": "Em pagamento"},
             "firstTimeIn": "2026-02-01T10:00:00Z", "lastTimeOut": None, "duration": None},
        ],
    }


# ── Testes básicos ─────────────────────────────────────────────────────────────

def test_extract_code_from_title():
    assert _extract_code("008.2026 - Legaliza Coelhinha") == "008.2026"
    assert _extract_code("001.2026 - AM do Amor") == "001.2026"
    assert _extract_code("OP.MPR-26.1-015 Quanta Musical") is None
    assert _extract_code("") is None


def test_normalize_cpf_cnpj():
    assert _normalize_cpf_cnpj("123.456.789-09") == "12345678909"
    assert _normalize_cpf_cnpj("12.345.678/0001-95") == "12345678000195"
    assert _normalize_cpf_cnpj("") is None
    assert _normalize_cpf_cnpj("12345") is None  # comprimento inválido


def test_transform_card_basic():
    card = _base_card()
    result = transform_card(card)

    assert result["card_id"] == "123456789"
    assert result["para_revisao"] is False

    # cliente
    assert result["cliente"]["nome"] == "Jeane Coelho de Mello"
    assert result["cliente"]["cpf_cnpj"] is None  # campo vazio no fixture
    assert result["cliente"]["external_source"] == "pipefy_financeiro"

    # código extraído do título (chave do filtro no sync)
    assert result["codigo"] == "008.2026"

    # projeto_externo
    assert result["projeto_externo"]["external_id"] == "008.2026"
    assert "Legaliza" in result["projeto_externo"]["nome"]

    # contrato
    assert result["contrato"]["numero"] == "008.2026"
    assert result["contrato"]["valor_total"] == Decimal("4000")
    assert result["contrato"]["quantidade_parcelas"] == 2
    assert result["contrato"]["fase_atual"] == "Em pagamento"


def test_pivot_parcelas_2x():
    card = _base_card(qtd_parcelas="2", valor="4000")
    result = transform_card(card)
    parcelas = result["parcelas"]

    assert len(parcelas) == 2
    # Valor dividido igualmente
    assert parcelas[0]["valor"] == Decimal("2000.00")
    assert parcelas[1]["valor"] == Decimal("2000.00")
    # Status
    assert parcelas[0]["status"] == "pago"
    assert parcelas[1]["status"] == "pendente"
    # external_id
    assert parcelas[0]["external_id"] == "123456789-p1"
    assert parcelas[1]["external_id"] == "123456789-p2"


def test_pivot_parcelas_arredondamento():
    """R$ 100 em 3 parcelas: 33.33 + 33.33 + 33.34"""
    card = _base_card(qtd_parcelas="3", valor="100")
    result = transform_card(card)
    parcelas = result["parcelas"]
    assert len(parcelas) == 3
    total = sum(p["valor"] for p in parcelas)
    assert total == Decimal("100")
    assert parcelas[2]["valor"] == Decimal("33.34")  # última absorve resto


def test_valor_variavel_para_revisao():
    card = _base_card()
    # Força campo "Possui Valor Variável" = Sim
    card["fields"].append(_make_field("possui_valor_vari_vel_ou_extra", "Sim"))
    # Remove o campo anterior
    card["fields"] = [f for f in card["fields"] if f["field"]["id"] != "possui_valor_vari_vel_ou_extra" or f["value"] == "Sim"]
    result = transform_card(card)
    assert result["para_revisao"] is True
    assert result["parcelas"] == []  # não gera parcelas


def test_sem_codigo_no_titulo_e_ignorado_pelo_sync():
    """Título sem NNN.YYYY → codigo=None. O sync usa isso pra descartar o card
    (não grava nada). O transform ainda calcula um placeholder, mas ele nunca
    é persistido porque o sync ignora o card antes do load."""
    card = _base_card(title="OP.MPR-26.1-015 Quanta Musical")
    result = transform_card(card)
    assert result["codigo"] is None


def test_data_inicio_pagamento():
    card = _base_card()
    result = transform_card(card)
    from datetime import datetime
    assert result["contrato"]["data_inicio_pagamento"] == datetime(2026, 2, 1, 10, 0, 0)


def test_datas_mensais_incrementam_30_dias():
    from datetime import date, timedelta
    card = _base_card(qtd_parcelas="3", valor="300")
    result = transform_card(card)
    parcelas = result["parcelas"]
    base = date(2026, 3, 1)
    assert parcelas[0]["data_vencimento"] == base
    assert parcelas[1]["data_vencimento"] == base + timedelta(days=30)
    assert parcelas[2]["data_vencimento"] == base + timedelta(days=60)
