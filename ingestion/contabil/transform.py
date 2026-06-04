"""transform.py — Linha crua da planilha -> dict pronto pra `transacao`.

Inclui a regra de idempotência (external_id = hash de conteúdo + contador de ocorrência),
fechada com o Davi. Funções puras: não tocam banco. O matching de conta/célula/categoria/
projeto (que precisa de banco) acontece no load/sync; aqui só normalizamos e marcamos
revisão.
"""

import hashlib
from typing import Optional

from .normalize import (
    EXTERNAL_SOURCE, norm_text, parse_tipo, map_setor, parse_valor, extract_codigo,
)


def _external_id(data, conta_key: str, tipo: str, setor_key: str,
                 categoria_key: str, valor: float, obs_key: str,
                 contador: dict) -> str:
    """sha1(conteúdo)[:16] + '-N', onde N desambígua duplicatas legítimas idênticas.

    Estável a reordenação de linhas; o contador conta na ordem de leitura da planilha.
    """
    base = f"{data.isoformat()}|{conta_key}|{tipo}|{setor_key}|{categoria_key}|{valor:.2f}|{obs_key}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    contador[h] = contador.get(h, 0) + 1
    return f"{h}-{contador[h]}"


def transform_row(raw: dict, contador: dict) -> dict:
    """Transforma uma linha crua (já filtrada: tem data) num dict de transação.

    Devolve sempre um dict com:
      - dados normalizados (conta_nome, tipo, celula_nome, categoria_nome, codigo, valor…)
      - external_source / external_id
      - "gravavel": bool — False se faltar campo NOT NULL (conta/tipo/valor)
      - "revisao": list[str] — motivos (setor desconhecido, categoria vazia, sem conta…)
    """
    revisao: list[str] = []

    conta_nome = norm_text(raw.get("conta"))
    tipo = parse_tipo(raw.get("tipo"))
    valor = parse_valor(raw.get("valor"))
    categoria_nome = norm_text(raw.get("categoria"))
    celula_nome, setor_ok = map_setor(raw.get("setor"))
    codigo = extract_codigo(raw.get("projeto"))
    obs = norm_text(raw.get("obs"))

    ref = f"linha {raw.get('row_num')} ({raw['data'].isoformat()}"
    ref += f", {obs})" if obs else ")"

    if not conta_nome:
        revisao.append(f"sem conta — {ref}")
    if tipo is None:
        revisao.append(f"sem tipo entrada/saída — {ref}")
    if valor is None:
        revisao.append(f"sem valor — {ref}")
    if categoria_nome is None:
        revisao.append(f"sem categoria — {ref}")
    if raw.get("setor") is not None and not setor_ok:
        revisao.append(f"setor desconhecido '{norm_text(raw.get('setor'))}' — {ref}")

    # external_id é determinístico sobre o conteúdo normalizado (chaves), mesmo quando a
    # linha não é gravável — assim o contador é estável entre execuções.
    external_id = _external_id(
        raw["data"],
        conta_key=(conta_nome or "").lower(),
        tipo=(tipo or ""),
        setor_key=(celula_nome or norm_text(raw.get("setor")) or "").lower(),
        categoria_key=(categoria_nome or "").lower(),
        valor=(valor or 0.0),
        obs_key=(obs or "").lower(),
        contador=contador,
    )

    gravavel = bool(conta_nome) and tipo is not None and valor is not None

    return {
        "data": raw["data"],
        "conta_nome": conta_nome,
        "tipo": tipo,
        "celula_nome": celula_nome,      # None = sem célula (Gerais/desconhecido)
        "categoria_nome": categoria_nome,  # None = categoria_id NULL
        "codigo": codigo,                # None = sem projeto vinculado
        "valor": valor,
        "obs": obs,
        "external_source": EXTERNAL_SOURCE,
        "external_id": external_id,
        "gravavel": gravavel,
        "revisao": revisao,
    }
