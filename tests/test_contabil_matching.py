"""Testes do matching de projeto do Controle Contábil (mocka o banco).

Regra: o código NNN.AAAA da planilha casa primeiro por `contrato.numero` (chave
estável — é o mesmo código e tem FK para o projeto). `projeto_externo.external_id`
é só fallback, porque reimportações (Pipefy/portfólio) trocam o external_id e
quebravam o vínculo das transações.
"""

import ingestion.contabil.matching as matching


def _fake_db(projetos, contratos):
    def fake_q(query, params=None, fetch_one=False, fetch_all=False):
        q = " ".join(query.split())
        if "FROM conta_bancaria" in q:
            return [{"id": 1, "nome": "Cora"}]
        if "FROM celula" in q:
            return []
        if "FROM categoria_transacao" in q:
            return []
        if "FROM projeto_externo" in q:
            return projetos
        if "FROM contrato" in q:
            return contratos
        return []
    return fake_q


def test_resolve_projeto_por_numero_de_contrato(monkeypatch):
    """external_id mudou na reimportação, mas contrato.numero ainda casa o código."""
    monkeypatch.setattr(matching, "execute_query", _fake_db(
        projetos=[{"id": 103, "external_id": "pipefy-card-987654"}],
        contratos=[{"numero": "010.2026", "projeto_externo_id": 103}],
    ))
    mapas = matching.carregar_mapas()
    assert matching.resolve_projeto(mapas, "010.2026") == 103


def test_resolve_projeto_fallback_external_id(monkeypatch):
    """Projeto sem contrato no banco ainda casa pelo external_id (comportamento antigo)."""
    monkeypatch.setattr(matching, "execute_query", _fake_db(
        projetos=[{"id": 72, "external_id": "006.2026"}],
        contratos=[],
    ))
    mapas = matching.carregar_mapas()
    assert matching.resolve_projeto(mapas, "006.2026") == 72


def test_contrato_tem_precedencia_sobre_external_id(monkeypatch):
    """Se divergirem, vale o contrato (fonte autoritativa do código NNN.AAAA)."""
    monkeypatch.setattr(matching, "execute_query", _fake_db(
        projetos=[{"id": 50, "external_id": "010.2026"}],
        contratos=[{"numero": "010.2026", "projeto_externo_id": 103}],
    ))
    mapas = matching.carregar_mapas()
    assert matching.resolve_projeto(mapas, "010.2026") == 103


def test_codigo_sem_match_continua_none(monkeypatch):
    monkeypatch.setattr(matching, "execute_query", _fake_db(projetos=[], contratos=[]))
    mapas = matching.carregar_mapas()
    assert matching.resolve_projeto(mapas, "999.2099") is None
    assert matching.resolve_projeto(mapas, None) is None
