"""sync.py — Orquestra parse -> transform -> seed -> load e devolve resumo.

Fonte = bytes do .xlsx (upload do n8n) ou caminho de arquivo (dry-run/local). Ordem de
carga: categoria_transacao -> transacao (respeita a FK).
"""

import io
import logging
from typing import Optional, Union

from .parser import parse_xlsx
from .transform import transform_row
from .seed import derive_categorias
from .matching import (
    carregar_mapas, resolve_conta, resolve_celula, resolve_categoria, resolve_projeto,
)
from .load import upsert_categoria, upsert_transacao
from .normalize import norm_key

logger = logging.getLogger("ingestion.contabil.sync")


def run_sync(source: Union[bytes, str, io.BytesIO, None] = None,
             dry_run: bool = False) -> dict:
    """
    Args:
        source: bytes do .xlsx, caminho do arquivo, ou file-like.
        dry_run: se True, roda parse/transform/seed-dry e NÃO grava.

    Returns:
        {
          "lidos": int,               # linhas de transação lidas (com data)
          "ignorados": int,           # não gravadas (faltou conta/tipo/valor ou conta inexistente)
          "inseridos": int,
          "atualizados": int,
          "categorias_criadas": int,
          "para_revisao": list[str],
          "erros": list[str],
        }
    """
    erros: list[str] = []
    para_revisao: list[str] = []

    if source is None:
        return {"lidos": 0, "ignorados": 0, "inseridos": 0, "atualizados": 0,
                "categorias_criadas": 0, "para_revisao": [],
                "erros": ["Nenhum arquivo recebido (source vazio)"]}

    try:
        brutas = parse_xlsx(source)
    except Exception as exc:
        logger.exception("Falha ao ler a planilha")
        return {"lidos": 0, "ignorados": 0, "inseridos": 0, "atualizados": 0,
                "categorias_criadas": 0, "para_revisao": [],
                "erros": [f"parse: {exc}"]}

    contador: dict[str, int] = {}
    transformadas = [transform_row(r, contador) for r in brutas]
    lidos = len(transformadas)

    for t in transformadas:
        para_revisao.extend(t["revisao"])

    categorias = derive_categorias(transformadas)

    # ── DRY-RUN: não toca no banco ────────────────────────────────────────────
    if dry_run:
        gravaveis = sum(1 for t in transformadas if t["gravavel"])
        logger.info(
            "[DRY-RUN] %d lidas | %d graváveis | %d categorias derivadas | %d p/ revisão",
            lidos, gravaveis, len(categorias), len(para_revisao),
        )
        return {
            "lidos": lidos,
            "ignorados": lidos - gravaveis,
            "inseridos": 0,
            "atualizados": 0,
            "categorias_criadas": len(categorias),
            "para_revisao": para_revisao,
            "erros": erros,
        }

    # ── 1. Semear categorias (antes das transações, por causa da FK) ──────────
    mapas = carregar_mapas()
    categorias_criadas = 0
    for c in categorias:
        try:
            celula_id = resolve_celula(mapas, c["celula_nome"])
            _, criada = upsert_categoria(c["nome"], c["tipo"], celula_id)
            if criada:
                categorias_criadas += 1
        except Exception as exc:
            logger.exception("Erro ao semear categoria %s", c["nome"])
            erros.append(f"categoria {c['nome']}: {exc}")

    # Recarrega o mapa de categorias com os ids recém-criados.
    mapas = carregar_mapas()

    # ── 2. Carregar transações ────────────────────────────────────────────────
    inseridos = 0
    atualizados = 0
    ignorados = 0

    for t in transformadas:
        ref = f"linha {t['data'].isoformat()}/{t['external_id']}"
        try:
            if not t["gravavel"]:
                ignorados += 1
                continue

            conta_id = resolve_conta(mapas, t["conta_nome"])
            if conta_id is None:
                ignorados += 1
                para_revisao.append(f"conta '{t['conta_nome']}' inexistente em conta_bancaria — {ref}")
                continue

            registro = {
                "data": t["data"],
                "conta_id": conta_id,
                "tipo": t["tipo"],
                "categoria_id": resolve_categoria(mapas, t["categoria_nome"]),
                "celula_id": resolve_celula(mapas, t["celula_nome"]),
                "valor": t["valor"],
                "projeto_externo_id": resolve_projeto(mapas, t["codigo"]),
                "external_id": t["external_id"],
                "external_source": t["external_source"],
            }
            if upsert_transacao(registro):
                inseridos += 1
            else:
                atualizados += 1
        except Exception as exc:
            logger.exception("Erro ao gravar transação %s", ref)
            erros.append(f"{ref}: {exc}")

    return {
        "lidos": lidos,
        "ignorados": ignorados,
        "inseridos": inseridos,
        "atualizados": atualizados,
        "categorias_criadas": categorias_criadas,
        "para_revisao": para_revisao,
        "erros": erros,
    }
