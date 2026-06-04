"""Teste do filtro de sync: card sem código de contrato no título não entra no banco.

Mocka o Pipefy (fetch_all_cards) e todos os upserts (load.py) — não toca em banco
nem em rede. Garante a regra fechada com o Davi: sem NNN.YYYY no título → ignorado.
"""

import ingestion.pipefy.sync as sync


def _field(field_id: str, value: str = "") -> dict:
    return {"name": field_id, "value": value, "array_value": None,
            "field": {"id": field_id, "type": "short_text"}}


def _card(card_id: str, title: str) -> dict:
    return {
        "id": card_id,
        "title": title,
        "current_phase": {"name": "Em pagamento"},
        "phases_history": [],
        "fields": [
            _field("cliente", "Fulano de Tal"),
            _field("forma_de_pagamento", "Boleto"),
            _field("valor_total_do_contrato", "1000"),
            _field("quantidade_de_parcelas", ""),  # sem parcelas → simplifica
        ],
    }


def test_card_sem_codigo_e_ignorado(monkeypatch):
    cards = [
        _card("111", "008.2026 - Com Código"),       # entra
        _card("222", "OP.MPR-26.1-015 Sem Código"),  # ignorado
    ]

    chamados = {"contrato": 0, "cliente": 0, "projeto": 0}

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter(cards))
    monkeypatch.setattr(sync, "upsert_forma_pagamento", lambda nome: 1)

    def _cliente(c):
        chamados["cliente"] += 1
        return 10
    monkeypatch.setattr(sync, "upsert_cliente", _cliente)

    def _projeto(p):
        chamados["projeto"] += 1
        return 20
    monkeypatch.setattr(sync, "upsert_projeto_externo", _projeto)

    def _contrato(c):
        chamados["contrato"] += 1
        return (30, True)  # (id, inserido)
    monkeypatch.setattr(sync, "upsert_contrato", _contrato)
    monkeypatch.setattr(sync, "upsert_contrato_pagamento", lambda p: None)

    resumo = sync.run_sync()

    assert resumo["lidos"] == 2
    assert resumo["ignorados"] == 1          # o "222" não entrou
    assert resumo["inseridos"] == 1          # só o "111"
    # nenhuma escrita disparada para o card ignorado
    assert chamados == {"contrato": 1, "cliente": 1, "projeto": 1}
