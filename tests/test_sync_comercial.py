"""Testes do sync comercial — foco na orquestração (mockam Pipefy e banco).

Cobrem o caminho incremental run_sync_card (ingestão por webhook) e garantem que
o full sync run_sync continua funcionando após o refactor que extraiu o corpo do
loop para _process_card.
"""

import ingestion.pipefy_comercial.sync as sync


def _fake_result(status: str = "ativo") -> dict:
    """Saída mínima de transform_card — sem origens/motivos/fases para isolar a
    orquestração (transform já tem seus próprios testes)."""
    return {
        "lead": {"nome": "Fulano"},
        "oportunidade": {"fase_atual_nome": "Lead", "status_terminal": status},
        "origens": [],
        "motivos": [],
        "phase_events": [],
        "_coord_sigla": None,
        "_origem_ref": None,
        "_motivo_ref": None,
    }


def _mock_loads(monkeypatch, inserido: bool = True):
    monkeypatch.setattr(sync, "transform_card", lambda card: _fake_result())
    monkeypatch.setattr(sync, "resolve_coordenacao", lambda sigla: None)
    monkeypatch.setattr(sync, "upsert_dim_origem", lambda sf, rv: (1, False))
    monkeypatch.setattr(sync, "upsert_dim_motivo", lambda sf, rv: (1, False))
    monkeypatch.setattr(sync, "upsert_lead", lambda lead: 1)
    monkeypatch.setattr(sync, "upsert_oportunidade", lambda opp: (10, inserido))
    monkeypatch.setattr(sync, "upsert_phase_event", lambda ev: True)


def test_run_sync_card_processa_um_card(monkeypatch):
    _mock_loads(monkeypatch, inserido=True)
    monkeypatch.setattr(sync, "fetch_card_by_id", lambda cid: {"id": cid})

    resumo = sync.run_sync_card("999")

    assert resumo["lidos"] == 1
    assert resumo["inseridos"] == 1
    assert resumo["atualizados"] == 0
    assert resumo["erros"] == []


def test_run_sync_card_existente_atualiza(monkeypatch):
    _mock_loads(monkeypatch, inserido=False)
    monkeypatch.setattr(sync, "fetch_card_by_id", lambda cid: {"id": cid})

    resumo = sync.run_sync_card("999")

    assert resumo["inseridos"] == 0
    assert resumo["atualizados"] == 1


def test_run_sync_card_nao_encontrado(monkeypatch):
    """Card deletado entre o evento e a chamada → fetch retorna None, sem crash."""
    _mock_loads(monkeypatch)
    monkeypatch.setattr(sync, "fetch_card_by_id", lambda cid: None)

    resumo = sync.run_sync_card("inexistente")

    assert resumo["lidos"] == 0
    assert resumo["inseridos"] == 0
    assert len(resumo["erros"]) == 1


def test_run_sync_card_dry_run_nao_grava(monkeypatch):
    chamou = {"opp": False}

    def _opp(opp):
        chamou["opp"] = True
        return (10, True)

    _mock_loads(monkeypatch)
    monkeypatch.setattr(sync, "upsert_oportunidade", _opp)
    monkeypatch.setattr(sync, "fetch_card_by_id", lambda cid: {"id": cid})

    resumo = sync.run_sync_card("999", dry_run=True)

    assert chamou["opp"] is False          # não gravou
    assert resumo["inseridos"] == 0
    assert resumo["lidos"] == 1


def test_run_sync_full_continua_funcionando(monkeypatch):
    """Refactor preservou o full sync: 2 cards → 2 lidos."""
    _mock_loads(monkeypatch, inserido=True)
    monkeypatch.setattr(sync, "fetch_all_cards", lambda: iter([{"id": "1"}, {"id": "2"}]))

    resumo = sync.run_sync()

    assert resumo["lidos"] == 2
    assert resumo["inseridos"] == 2
    assert resumo["erros"] == []


def test_run_delete_card_remove(monkeypatch):
    """card.delete → remove a oportunidade pela chave externa."""
    chamado = {}

    def _del(source, ext_id):
        chamado["args"] = (source, ext_id)
        return 1

    monkeypatch.setattr(sync, "delete_oportunidade_by_external", _del)

    resumo = sync.run_delete_card("999")

    assert chamado["args"] == (sync.EXTERNAL_SOURCE, "999")
    assert resumo["removidos"] == 1
    assert resumo["erros"] == []


def test_run_delete_card_idempotente(monkeypatch):
    """Oportunidade já inexistente → removidos=0, sem erro."""
    monkeypatch.setattr(sync, "delete_oportunidade_by_external", lambda s, e: 0)

    resumo = sync.run_delete_card("inexistente")

    assert resumo["removidos"] == 0
    assert resumo["erros"] == []


def test_run_delete_card_dry_run_nao_remove(monkeypatch):
    chamou = {"del": False}

    def _del(s, e):
        chamou["del"] = True
        return 1

    monkeypatch.setattr(sync, "delete_oportunidade_by_external", _del)

    resumo = sync.run_delete_card("999", dry_run=True)

    assert chamou["del"] is False
    assert resumo["removidos"] == 0
