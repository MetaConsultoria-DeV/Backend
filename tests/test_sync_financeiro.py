"""Testes do sync do financeiro (mockam Pipefy e banco — sem rede/DB).

Cobrem duas regras fechadas com o Davi:
1. Card sem código de contrato no título → ignorado (não entra nada).
2. Contrato cujo número já existe → o bot NÃO duplica: reusa e atualiza só a fase.
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


def _mock_loads(monkeypatch, chamados):
    """Mocka todos os upserts de escrita e devolve o dict de contadores."""
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

    def _fase(contrato_id, fase, ini, fim):
        chamados["fase"] += 1
    monkeypatch.setattr(sync, "atualizar_fase_contrato", _fase)


def test_card_sem_codigo_e_ignorado(monkeypatch):
    cards = [
        _card("111", "008.2026 - Com Código"),       # entra
        _card("222", "OP.MPR-26.1-015 Sem Código"),  # ignorado
    ]
    chamados = {"contrato": 0, "cliente": 0, "projeto": 0, "fase": 0}

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter(cards))
    monkeypatch.setattr(sync, "resolve_contrato_por_numero", lambda numero: None)  # nada existe
    _mock_loads(monkeypatch, chamados)

    resumo = sync.run_sync()

    assert resumo["lidos"] == 2
    assert resumo["ignorados"] == 1          # o "222" não entrou
    assert resumo["inseridos"] == 1          # só o "111"
    assert chamados == {"contrato": 1, "cliente": 1, "projeto": 1, "fase": 0}


def test_contrato_existente_nao_duplica(monkeypatch):
    """Número já no banco → reusa, atualiza só a fase, e NÃO cria projeto/contrato."""
    cards = [_card("333", "008.2026 - Já Existe")]
    chamados = {"contrato": 0, "cliente": 0, "projeto": 0, "fase": 0}

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter(cards))
    # contrato 008.2026 já existe, ligado ao projeto 99
    monkeypatch.setattr(sync, "resolve_contrato_por_numero",
                        lambda numero: {"id": 77, "projeto_externo_id": 99})
    _mock_loads(monkeypatch, chamados)

    resumo = sync.run_sync()

    assert resumo["lidos"] == 1
    assert resumo["inseridos"] == 0          # nada criado
    assert resumo["atualizados"] == 1        # só atualizou a fase
    # NÃO chamou projeto/contrato/cliente; chamou só a atualização de fase
    assert chamados == {"contrato": 0, "cliente": 0, "projeto": 0, "fase": 1}
