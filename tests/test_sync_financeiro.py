"""Testes do sync do financeiro (mockam Pipefy e banco — sem rede/DB).

Regras cobertas:
1. Card sem código de contrato no título → ignorado (não entra nada).
2. Contrato cujo número já existe → o bot NÃO duplica (não cria projeto nem
   contrato novos), mas COMPLETA o contrato existente com os dados do Pipefy
   (valor, cliente, fase) e grava as parcelas nele. Antes ele só atualizava a
   fase, e contratos criados pelo app ficavam para sempre com R$ 0 e 0/0
   parcelas mesmo com o card cheio no Pipefy.
"""

import ingestion.pipefy.sync as sync


def _field(field_id: str, value: str = "") -> dict:
    return {"name": field_id, "value": value, "array_value": None,
            "field": {"id": field_id, "type": "short_text"}}


def _card(card_id: str, title: str, parcelas: int = 0, pagas: int = 0) -> dict:
    fields = [
        _field("cliente", "Fulano de Tal"),
        _field("forma_de_pagamento", "Boleto"),
        _field("valor_total_do_contrato", "1000"),
        _field("quantidade_de_parcelas", str(parcelas) if parcelas else ""),
    ]
    # Checkboxes "Nª Parcela Paga" (mesmos ids do field_map)
    from ingestion.pipefy.field_map import PARCELA_FIELD_IDS
    for n in range(pagas):
        fields.append(_field(PARCELA_FIELD_IDS[n], "1ª Parcela Paga"))
    return {
        "id": card_id,
        "title": title,
        "current_phase": {"name": "Em pagamento"},
        "phases_history": [],
        "fields": fields,
    }


def _mock_loads(monkeypatch, chamados, parcelas_gravadas=None):
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

    def _parcela(p):
        chamados["parcela"] += 1
        if parcelas_gravadas is not None:
            parcelas_gravadas.append(p)
    monkeypatch.setattr(sync, "upsert_contrato_pagamento", _parcela)

    def _completar(contrato_id, contrato, cliente_id, forma_id):
        chamados["completar"] += 1
    monkeypatch.setattr(sync, "completar_contrato_existente", _completar)


def test_card_sem_codigo_e_ignorado(monkeypatch):
    cards = [
        _card("111", "008.2026 - Com Código"),       # entra
        _card("222", "OP.MPR-26.1-015 Sem Código"),  # ignorado
    ]
    chamados = {"contrato": 0, "cliente": 0, "projeto": 0, "parcela": 0, "completar": 0}

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter(cards))
    monkeypatch.setattr(sync, "resolve_contrato_por_numero", lambda numero: None)  # nada existe
    _mock_loads(monkeypatch, chamados)

    resumo = sync.run_sync()

    assert resumo["lidos"] == 2
    assert resumo["ignorados"] == 1          # o "222" não entrou
    assert resumo["inseridos"] == 1          # só o "111"
    assert chamados == {"contrato": 1, "cliente": 1, "projeto": 1, "parcela": 0, "completar": 0}


def test_contrato_existente_completa_dados_sem_duplicar(monkeypatch):
    """Número já no banco → NÃO cria projeto/contrato novos, mas completa o
    contrato existente (valor/cliente/fase) e grava as parcelas do card nele."""
    cards = [_card("333", "008.2026 - Já Existe", parcelas=2, pagas=1)]
    chamados = {"contrato": 0, "cliente": 0, "projeto": 0, "parcela": 0, "completar": 0}
    parcelas_gravadas: list[dict] = []

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter(cards))
    # contrato 008.2026 já existe, ligado ao projeto 99 e cliente 55
    monkeypatch.setattr(sync, "resolve_contrato_por_numero",
                        lambda numero: {"id": 77, "projeto_externo_id": 99, "cliente_id": 55})
    _mock_loads(monkeypatch, chamados, parcelas_gravadas)

    resumo = sync.run_sync()

    assert resumo["lidos"] == 1
    assert resumo["inseridos"] == 0          # nada criado
    assert resumo["atualizados"] == 1
    # NÃO criou projeto/contrato; completou o existente e gravou as 2 parcelas
    assert chamados["projeto"] == 0
    assert chamados["contrato"] == 0
    assert chamados["completar"] == 1
    assert chamados["parcela"] == 2
    # Parcelas apontam para o contrato/projeto EXISTENTES (não para entidades novas)
    assert all(p["contrato_id"] == 77 for p in parcelas_gravadas)
    assert all(p["projeto_externo_id"] == 99 for p in parcelas_gravadas)
    assert parcelas_gravadas[0]["status"] == "pago"      # 1ª marcada no card
    assert parcelas_gravadas[1]["status"] == "pendente"  # 2ª não marcada


def test_contrato_existente_sem_cliente_no_card_usa_cliente_atual(monkeypatch):
    """Card sem nome de cliente → não cria cliente vazio; parcela usa o cliente
    que o contrato já tem."""
    card = _card("444", "009.2026 - Sem Cliente", parcelas=1)
    card["fields"] = [f for f in card["fields"] if f["field"]["id"] != "cliente"]
    chamados = {"contrato": 0, "cliente": 0, "projeto": 0, "parcela": 0, "completar": 0}
    parcelas_gravadas: list[dict] = []

    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter([card]))
    monkeypatch.setattr(sync, "resolve_contrato_por_numero",
                        lambda numero: {"id": 88, "projeto_externo_id": 99, "cliente_id": 55})
    _mock_loads(monkeypatch, chamados, parcelas_gravadas)

    sync.run_sync()

    assert chamados["cliente"] == 0                       # não criou cliente vazio
    assert parcelas_gravadas[0]["cliente_id"] == 55       # herdou do contrato
