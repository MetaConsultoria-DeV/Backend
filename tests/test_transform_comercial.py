"""Testes unitários do transform comercial — não precisam de banco nem de Pipefy."""

from decimal import Decimal
from datetime import datetime

from ingestion.pipefy_comercial.transform import (
    transform_card, _parse_money, _build_phase_events,
)


# ── Helpers de fixture ────────────────────────────────────────────────────────

def _f(field_id, value="", array_value=None):
    return {"name": field_id, "value": value, "array_value": array_value,
            "field": {"id": field_id, "type": "short_text"}}


def _card(card_id="734299001", fase_id="5170380", fase_nome="Caixa de Entrada",
          labels=None, fields=None, history=None,
          created="2026-05-01T09:00:00Z", finished=None):
    return {
        "id": card_id,
        "title": f"N 5329 - Arquiteta Horizon",
        "current_phase": {"id": fase_id, "name": fase_nome},
        "createdAt": created,
        "finished_at": finished,
        "labels": labels if labels is not None else [{"name": "OP"}],
        "fields": fields if fields is not None else [
            _f("nome", "Maria Clara Firmino"),
            _f("contact_e_mail", "maria@horizon.com"),
            _f("contact_phone", "21999990000"),
            _f("company_name", "Arquiteta Horizon"),
            _f("profiss_o", "Arquiteta"),
            _f("como_o_cliente_conheceu_a_meta", "Indicação"),
            _f("respons_veis_pela_negocia_o", "", array_value=["Davi Moreno", "Felipe Souto"]),
        ],
        "phases_history": history if history is not None else [
            {"phase": {"id": "5170380", "name": "Caixa de Entrada"},
             "firstTimeIn": "2026-05-01T09:00:00Z", "lastTimeOut": "2026-05-02T09:00:00Z",
             "duration": 86400},
        ],
    }


# ── parse_money ───────────────────────────────────────────────────────────────

def test_parse_money_formatos():
    assert _parse_money("5300.0") == Decimal("5300.0")        # API normalizada
    assert _parse_money("R$ 5.300,00") == Decimal("5300.00")  # BR com milhar
    assert _parse_money("5300,00") == Decimal("5300.00")      # BR sem milhar
    assert _parse_money("") is None
    assert _parse_money(None) is None


# ── lead ──────────────────────────────────────────────────────────────────────

def test_lead_basico():
    r = transform_card(_card())
    lead = r["lead"]
    assert lead["nome"] == "Maria Clara Firmino"
    assert lead["email"] == "maria@horizon.com"
    assert lead["empresa"] == "Arquiteta Horizon"
    assert lead["cargo"] == "Arquiteta"
    assert lead["external_source"] == "pipefy_comercial"
    assert lead["external_id"] == "734299001"


def test_responsaveis_junta_lista():
    r = transform_card(_card())
    assert r["oportunidade"]["responsaveis"] == "Davi Moreno, Felipe Souto"


# ── status_terminal ───────────────────────────────────────────────────────────

def test_status_terminal_ativo_default():
    r = transform_card(_card(fase_id="5170380", fase_nome="Caixa de Entrada"))
    assert r["oportunidade"]["status_terminal"] == "ativo"


def test_status_terminal_fechado():
    r = transform_card(_card(fase_id="4984603", fase_nome="Fechados"))
    assert r["oportunidade"]["status_terminal"] == "fechado"


def test_status_terminal_email_mkt_vira_postergado():
    r = transform_card(_card(fase_id="339067237", fase_nome="Email Mkt"))
    assert r["oportunidade"]["status_terminal"] == "postergado"


def test_status_terminal_desistido_recusado_postergado():
    assert transform_card(_card(fase_id="5172117"))["oportunidade"]["status_terminal"] == "desistido"
    assert transform_card(_card(fase_id="5153362"))["oportunidade"]["status_terminal"] == "recusado"
    assert transform_card(_card(fase_id="8098613"))["oportunidade"]["status_terminal"] == "postergado"
    assert transform_card(_card(fase_id="313949699"))["oportunidade"]["status_terminal"] == "postergado"


# ── origem ────────────────────────────────────────────────────────────────────

def test_origem_start_form():
    r = transform_card(_card())
    assert {"source_field": "start_form", "raw_value": "Indicação"} in r["origens"]
    assert r["_origem_ref"]["source_field"] == "start_form"


def test_origem_ld_tem_prioridade():
    fields = [
        _f("nome", "X"),
        _f("como_o_cliente_conheceu_a_meta", "Google"),
        _f("como_o_lead_conheceu_a_meta", "Indicação de cliente"),
    ]
    r = transform_card(_card(fields=fields))
    assert len(r["origens"]) == 2
    # ld vence start_form na referência da oportunidade
    assert r["_origem_ref"]["source_field"] == "ld"
    assert r["_origem_ref"]["raw_value"] == "Indicação de cliente"


# ── motivo de perda ───────────────────────────────────────────────────────────

def test_motivo_perda_extraido():
    fields = [
        _f("nome", "X"),
        _f("por_qual_motivo_o_projeto_entrou_em_desistidos", "Sem orçamento"),
    ]
    r = transform_card(_card(fase_id="5172117", fields=fields))
    assert r["_motivo_ref"]["raw_value"] == "Sem orçamento"
    assert r["_motivo_ref"]["source_field"] == "por_qual_motivo_o_projeto_entrou_em_desistidos"


# ── coordenação (etiqueta) ────────────────────────────────────────────────────

def test_coord_label_op():
    r = transform_card(_card(labels=[{"name": "OP"}, {"name": "Quente"}]))
    assert r["_coord_sigla"] == "OP"


def test_coord_label_cp_vira_none():
    # CP e ND não têm linha em coordenacao → ignorados aqui (None)
    r = transform_card(_card(labels=[{"name": "CP"}, {"name": "ND"}, {"name": "Civil"}]))
    assert r["_coord_sigla"] is None


# ── phase history / duração ───────────────────────────────────────────────────

def test_phase_events_transicoes_e_duracao():
    history = [
        {"phase": {"id": "5170380", "name": "Caixa de Entrada"},
         "firstTimeIn": "2026-05-01T09:00:00Z", "lastTimeOut": "2026-05-02T09:00:00Z",
         "duration": 86400},
        {"phase": {"id": "5153363", "name": "Ligação Diagnóstico"},
         "firstTimeIn": "2026-05-02T09:00:00Z", "lastTimeOut": None, "duration": None},
    ]
    events = _build_phase_events(_card(history=history))
    assert len(events) == 2
    # 1º evento: entrada na Caixa de Entrada, sem fase anterior
    assert events[0]["from_phase_id"] is None
    assert events[0]["to_phase_id"] == "5170380"
    assert events[0]["duration_previous_phase_seconds"] is None
    # 2º evento: veio da Caixa de Entrada (86400s) para a LD
    assert events[1]["from_phase_id"] == "5170380"
    assert events[1]["to_phase_id"] == "5153363"
    assert events[1]["duration_previous_phase_seconds"] == 86400
    assert events[1]["moved_at"] == datetime(2026, 5, 2, 9, 0, 0)
    assert events[1]["external_event_id"] == "734299001:5153363:2026-05-02T09:00:00"
    assert events[1]["external_source"] == "pipefy_comercial_phase"


def test_oportunidade_timestamps_e_chaves():
    r = transform_card(_card(finished="2026-05-10T18:00:00Z", fase_id="4984603"))
    opp = r["oportunidade"]
    assert opp["criado_em"] == datetime(2026, 5, 1, 9, 0, 0)
    assert opp["finalizado_em"] == datetime(2026, 5, 10, 18, 0, 0)
    assert opp["external_id"] == "734299001"
    assert opp["fase_atual_id"] == "4984603"
