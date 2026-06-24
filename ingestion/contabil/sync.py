"""Module for orchestrating the Controle Contábil synchronization process.

Coordinates the complete data pipeline lifecycle:
1. Parsing: Reads the raw Excel workbook and extracts rows.
2. Transformation: Cleans and standardizes raw rows.
3. Derivation: Dynamically extracts categories from transaction lines.
4. Seeding: Upserts unique transaction categories (parent tables first to satisfy foreign keys).
5. Load: Upserts individual transactions mapping foreign keys via cached memory lookups.
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

# Logger instance for the synchronization process
logger = logging.getLogger("ingestion.contabil.sync")


def run_sync(source: Union[bytes, str, io.BytesIO, None] = None,
             dry_run: bool = False) -> dict:
    """Executes the Controle Contábil spreadsheet synchronization pipeline.

    Reads accounting transactions from the spreadsheet, resolves and inserts missing
    categories, matches database entities (accounts, cells, projects, contracts), and performs
    upsert operations on transaction records.

    Args:
        source (Union[bytes, str, io.BytesIO, None]): The Excel file content as bytes,
            a local file path string, or a file-like BytesIO stream.
        dry_run (bool): If True, parses, transforms, and derives categories, but skips
            all database insertions and updates.

    Returns:
        dict: A summary dictionary containing the sync execution metrics:
            - lidos (int): Total number of transaction rows parsed from the spreadsheet.
            - ignorados (int): Rows skipped due to formatting errors or missing entities.
            - inseridos (int): Count of new transactions written to the database.
            - atualizados (int): Count of existing transactions updated in the database.
            - vinculadas (int): Count of transactions successfully linked to a project.
            - categorias_criadas (int): Count of new transaction categories created.
            - para_revisao (list[str]): List of warnings/anomalies requiring manual review.
            - erros (list[str]): List of execution errors encountered during the run.
    """
    erros: list[str] = []
    para_revisao: list[str] = []

    if source is None:
        return {"lidos": 0, "ignorados": 0, "inseridos": 0, "atualizados": 0,
                "vinculadas": 0, "categorias_criadas": 0, "para_revisao": [],
                "erros": ["Nenhum arquivo recebido (source vazio)"]}

    # --- Phase 1: Parse Excel ---
    try:
        brutas = parse_xlsx(source)
    except Exception as exc:
        logger.exception("Falha ao ler a planilha")
        return {"lidos": 0, "ignorados": 0, "inseridos": 0, "atualizados": 0,
                "vinculadas": 0, "categorias_criadas": 0, "para_revisao": [],
                "erros": [f"parse: {exc}"]}

    # --- Phase 2: Transform Rows ---
    # Keeps track of index-based occurrences to generate unique external IDs.
    contador: dict[str, int] = {}
    transformadas = [transform_row(r, contador) for r in brutas]
    lidos = len(transformadas)

    # Collect validation warnings/messages generated during transformation
    for t in transformadas:
        para_revisao.extend(t["revisao"])

    # --- Phase 3: Derive Categories ---
    categorias = derive_categorias(transformadas)

    # --- Phase 4: Dry Run check ---
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
            "vinculadas": 0,
            "categorias_criadas": len(categorias),
            "para_revisao": para_revisao,
            "erros": erros,
        }

    # --- Phase 5: Seed Categories (Parent entities first to respect DB constraints) ---
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

    # Reload database maps to ensure dynamically created categories are cached
    mapas = carregar_mapas()

    # --- Phase 6: Load Transactions ---
    inseridos = 0
    atualizados = 0
    ignorados = 0
    vinculadas = 0
    sem_vinculo: list[str] = []

    for t in transformadas:
        ref = f"linha {t['data'].isoformat()}/{t['external_id']}"
        try:
            # Skip rows marked as non-writable during the transformation phase
            if not t["gravavel"]:
                ignorados += 1
                continue

            # Verify the bank account exists in the database
            conta_id = resolve_conta(mapas, t["conta_nome"])
            if conta_id is None:
                ignorados += 1
                para_revisao.append(f"conta '{t['conta_nome']}' inexistente em conta_bancaria — {ref}")
                continue

            # Attempt to resolve project / contract link
            projeto_id = resolve_projeto(mapas, t["codigo"])
            if t["codigo"] and projeto_id is None:
                # Project code exists in spreadsheet but cannot be matched in the DB
                sem_vinculo.append(f"código '{t['codigo']}' sem projeto/contrato no banco — {ref}")
            elif projeto_id is not None:
                vinculadas += 1

            # Build database record mapping keys to resolved database foreign key IDs
            registro = {
                "data": t["data"],
                "conta_id": conta_id,
                "tipo": t["tipo"],
                "categoria_id": resolve_categoria(mapas, t["categoria_nome"]),
                "celula_id": resolve_celula(mapas, t["celula_nome"]),
                "valor": t["valor"],
                "projeto_externo_id": projeto_id,
                "external_id": t["external_id"],
                "external_source": t["external_source"],
            }
            # Commit transaction row to the database (upsert)
            if upsert_transacao(registro):
                inseridos += 1
            else:
                atualizados += 1
        except Exception as exc:
            logger.exception("Erro ao gravar transação %s", ref)
            erros.append(f"{ref}: {exc}")

    # Append project link warnings to review report
    para_revisao.extend(sem_vinculo)

    return {
        "lidos": lidos,
        "ignorados": ignorados,
        "inseridos": inseridos,
        "atualizados": atualizados,
        "vinculadas": vinculadas,
        "categorias_criadas": categorias_criadas,
        "para_revisao": para_revisao,
        "erros": erros,
    }

