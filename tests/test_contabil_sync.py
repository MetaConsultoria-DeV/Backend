"""Teste de integração do sync contábil: planilha -> parse -> transform -> resolve -> upsert.

Reproduz o caso real (jun/2026): a saída de 31/05 com código 010.2026 deve sair
vinculada ao projeto mesmo quando o external_id do projeto mudou numa reimportação
(o match vem de contrato.numero).
"""

import io
import datetime as dt

import openpyxl

import ingestion.contabil.sync as sync_mod
import ingestion.contabil.matching as matching


def _xlsx_bytes(rows: list[list]) -> bytes:
    """Monta um .xlsx com o layout do Controle Contábil (tabela nas colunas D..K)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None] * 3 + ["Data", "Conta", "Entrada/Saída", "Setor", "Categoria",
                            "Nº do Projeto", "Valor", "Observações"])
    for r in rows:
        ws.append([None] * 3 + r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fake_matching_db(monkeypatch):
    """Banco fake para os lookups: projeto com external_id trocado, contrato com o código."""
    def fake_q(query, params=None, fetch_one=False, fetch_all=False):
        q = " ".join(query.split())
        if "FROM conta_bancaria" in q:
            return [{"id": 1, "nome": "Cora"}]
        if "FROM celula" in q:
            return [{"id": 2, "nome": "Projetos"}]
        if "FROM categoria_transacao" in q:
            return [{"id": 3, "nome": "Impressões / ART / RRT"}]
        if "FROM projeto_externo" in q:
            return [{"id": 103, "external_id": "pipefy-card-987654"}]
        if "FROM contrato" in q:
            return [{"numero": "010.2026", "projeto_externo_id": 103}]
        return []
    monkeypatch.setattr(matching, "execute_query", fake_q)


def test_sync_vincula_transacao_pelo_numero_do_contrato(monkeypatch):
    _fake_matching_db(monkeypatch)

    gravadas: list[dict] = []
    monkeypatch.setattr(sync_mod, "upsert_transacao", lambda t: gravadas.append(t) or True)
    monkeypatch.setattr(sync_mod, "upsert_categoria", lambda nome, tipo, celula_id: (3, False))

    xlsx = _xlsx_bytes([
        [dt.datetime(2026, 5, 31), "Cora", "Saída", "Projetos",
         "Impressões / ART / RRT", "010.2026", 130.64, "CAU/RJ Mariconio"],
        [dt.datetime(2026, 5, 29), "Cora", "Saída", "Operações",
         "Manutenção", None, 95.46, "Tootz Solucoes Tecnologicas"],
    ])

    resumo = sync_mod.run_sync(xlsx)

    assert resumo["erros"] == []
    assert resumo["inseridos"] == 2
    assert resumo["vinculadas"] == 1
    assert gravadas[0]["projeto_externo_id"] == 103   # 010.2026 -> contrato -> projeto
    assert gravadas[0]["celula_id"] == 2
    assert gravadas[0]["categoria_id"] == 3
    assert gravadas[1]["projeto_externo_id"] is None  # sem código -> sem vínculo


def test_sync_codigo_sem_match_vai_para_revisao(monkeypatch):
    _fake_matching_db(monkeypatch)
    monkeypatch.setattr(sync_mod, "upsert_transacao", lambda t: True)
    monkeypatch.setattr(sync_mod, "upsert_categoria", lambda nome, tipo, celula_id: (3, False))

    xlsx = _xlsx_bytes([
        [dt.datetime(2026, 1, 17), "Cora", "Saída", "Projetos",
         "Transporte", "021.2025", 401.03, "Transporte Victor Dias"],
    ])

    resumo = sync_mod.run_sync(xlsx)

    assert resumo["vinculadas"] == 0
    assert any("021.2025" in r for r in resumo["para_revisao"])
