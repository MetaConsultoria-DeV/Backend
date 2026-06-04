"""Testes do transform e da idempotência (external_id = hash + contador)."""

import datetime as dt

from ingestion.contabil.transform import transform_row
from ingestion.contabil.seed import derive_categorias


def _raw(**kw):
    base = {
        "row_num": 11, "data": dt.date(2026, 6, 1), "conta": "Cora",
        "tipo": "Saída", "setor": "Operações", "categoria": "Clicksign",
        "projeto": "", "valor": 229.62, "obs": "Clicksign",
    }
    base.update(kw)
    return base


def test_transform_campos_normalizados():
    t = transform_row(_raw(), {})
    assert t["tipo"] == "saida"
    assert t["conta_nome"] == "Cora"
    assert t["celula_nome"] == "Operações"
    assert t["categoria_nome"] == "Clicksign"
    assert t["valor"] == 229.62
    assert t["gravavel"] is True
    assert t["revisao"] == []
    assert t["external_source"] == "sharepoint_caixa"


def test_external_id_estavel_entre_execucoes():
    """Mesmo conteúdo, dois 'runs' (contadores zerados) -> mesmo external_id."""
    a = transform_row(_raw(), {})
    b = transform_row(_raw(), {})
    assert a["external_id"] == b["external_id"]


def test_external_id_contador_desambigua_duplicatas():
    """Duas linhas idênticas no MESMO arquivo -> -1 e -2 (não colapsam)."""
    contador = {}
    a = transform_row(_raw(), contador)
    b = transform_row(_raw(), contador)
    assert a["external_id"].endswith("-1")
    assert b["external_id"].endswith("-2")
    assert a["external_id"] != b["external_id"]


def test_external_id_muda_com_conteudo():
    contador = {}
    a = transform_row(_raw(valor=229.62), contador)
    b = transform_row(_raw(valor=999.00), contador)
    assert a["external_id"].split("-")[0] != b["external_id"].split("-")[0]


def test_codigo_projeto_extraido_ou_nulo():
    assert transform_row(_raw(projeto="010.2026"), {})["codigo"] == "010.2026"
    assert transform_row(_raw(projeto="ImpulseUp"), {})["codigo"] is None


def test_linha_sem_conta_nao_e_gravavel():
    t = transform_row(_raw(conta=None), {})
    assert t["gravavel"] is False
    assert any("sem conta" in r for r in t["revisao"])


def test_categoria_vazia_vai_para_revisao():
    t = transform_row(_raw(categoria=None), {})
    assert t["categoria_nome"] is None
    assert any("sem categoria" in r for r in t["revisao"])


def test_setor_desconhecido_vai_para_revisao():
    t = transform_row(_raw(setor="Departamento X"), {})
    assert t["celula_nome"] is None
    assert any("setor desconhecido" in r for r in t["revisao"])


def test_derive_categorias_funde_e_infere_tipo():
    rows = [
        transform_row(_raw(categoria="Camisas Polo ", tipo="Saída"), {}),
        transform_row(_raw(categoria="Camisas Polo", tipo="Saída"), {}),
        transform_row(_raw(categoria="ENEJ", tipo="Entrada"), {}),
        transform_row(_raw(categoria="ENEJ", tipo="Saída"), {}),
    ]
    cats = {c["nome"]: c for c in derive_categorias(rows)}
    # 'Camisas Polo ' e 'Camisas Polo' fundem numa só
    assert "Camisas Polo" in cats
    assert cats["Camisas Polo"]["tipo"] == "saida"
    # ENEJ aparece como entrada e saída -> ambos
    assert cats["ENEJ"]["tipo"] == "ambos"
