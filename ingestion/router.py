"""Module containing the internal routes for triggering synchronization workflows.

This router registers endpoints that handle manual or webhook-triggered runs
for Pipefy Financeiro, Pipefy Comercial (Sales Pipeline), and the Excel-based
Controle Contábil ingestion.
"""

import os
import logging
import secrets
from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File

from .pipefy.sync import run_sync
from .pipefy_comercial.sync import (
    run_sync as run_sync_comercial,
    run_sync_card as run_sync_comercial_card,
    run_delete_card as run_delete_comercial_card,
)
from .contabil.sync import run_sync as run_sync_contabil

# Set up logging for the ingestion router
logger = logging.getLogger("ingestion.router")
router = APIRouter(prefix="/internal", tags=["internal"])

def _check_token(x_internal_token: str | None) -> None:
    """Verifies the incoming request token against the configured internal sync token.

    Uses secrets.compare_digest for constant-time comparison to prevent timing attacks.
    The environment variable check is performed at call-time to ensure any dynamic dotenv
    updates are reflected.

    Args:
        x_internal_token (str | None): The token provided in the request's Header.

    Raises:
        HTTPException: 503 if INTERNAL_SYNC_TOKEN is not configured in environment variables.
        HTTPException: 401 if x_internal_token is missing or does not match the configured token.
    """
    internal_token = os.getenv("INTERNAL_SYNC_TOKEN", "")
    if not internal_token:
        raise HTTPException(status_code=503, detail="INTERNAL_SYNC_TOKEN não configurado")
    # compare_digest: constant-time comparison to prevent timing attacks
    if not x_internal_token or not secrets.compare_digest(x_internal_token, internal_token):
        raise HTTPException(status_code=401, detail="Token interno inválido ou ausente")


@router.post("/sync/pipefy-financeiro")
def sync_pipefy_financeiro(
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """Dispatches the Pipefy Financeiro to MySQL database synchronization.

    Retrieves finance pipeline cards, normalizes, transforms fields, matches existing records,
    and runs upsert operations.

    Args:
        dry_run (bool): If True, executes the entire pipeline without writing changes to the database.
        x_internal_token (str | None): Header token to authorize the request.

    Returns:
        JSONResponse: A response detailing the synchronization execution results, including
            synced count and errors, returning 200 on success or 207 if partial errors occurred.
    """
    _check_token(x_internal_token)

    logger.info("Iniciando sync Pipefy Financeiro (dry_run=%s)", dry_run)
    resultado = run_sync(dry_run=dry_run)
    logger.info("Sync concluído: %s", resultado)

    status_code = 200
    if resultado["erros"]:
        status_code = 207  # Multi-Status — partially successful ingestion

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)


@router.post("/sync/pipefy-comercial")
def sync_pipefy_comercial(
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """Dispatches the Pipefy Comercial (Sales Pipeline) to MySQL database synchronization.

    Fetches sales pipeline cards, normalizes and maps opportunity fields, resolves matching IDs,
    and commits updates.

    Args:
        dry_run (bool): If True, runs the pipeline without committing changes to the database.
        x_internal_token (str | None): Header token to authorize the request.

    Returns:
        JSONResponse: A response detailing the synchronization results, returning 200 on success
            or 207 if partial errors occurred.
    """
    _check_token(x_internal_token)

    logger.info("Iniciando sync Pipefy Comercial (dry_run=%s)", dry_run)
    resultado = run_sync_comercial(dry_run=dry_run)
    logger.info("Sync comercial concluído: %s", resultado)

    status_code = 207 if resultado["erros"] else 200

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)


@router.post("/sync/pipefy-comercial/card")
def sync_pipefy_comercial_card(
    card_id: str = Query(..., description="ID do card do Pipefy"),
    action: str | None = Query(
        default=None,
        description="Ação do webhook Pipefy. 'card.delete' remove a oportunidade; "
                    "qualquer outra (ou vazio) sincroniza o card.",
    ),
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """Ingests or deletes a single card from the Pipefy Comercial pipeline.

    Typically triggered by a webhook (via n8n) when a specific card's state changes.
    This operation is idempotent; calling it multiple times for the same card is safe.

    Args:
        card_id (str): The unique identifier of the target Pipefy card.
        action (str | None): Webhook action name. If set to 'card.delete', the corresponding opportunity
            in the database will be deleted. Any other value (or null) updates or creates the card.
        dry_run (bool): If True, performs the operation logic without writing to the database.
        x_internal_token (str | None): Header token to authorize the request.

    Returns:
        JSONResponse: Details of the single-card operation, returning 200 on success
            or 207 if errors occurred.
    """
    _check_token(x_internal_token)

    if action == "card.delete":
        logger.info("Delete card Pipefy Comercial card_id=%s (dry_run=%s)", card_id, dry_run)
        resultado = run_delete_comercial_card(card_id, dry_run=dry_run)
    else:
        logger.info("Sync single-card Pipefy Comercial card_id=%s action=%s (dry_run=%s)",
                    card_id, action, dry_run)
        resultado = run_sync_comercial_card(card_id, dry_run=dry_run)
    logger.info("Single-card concluído: %s", resultado)

    status_code = 207 if resultado["erros"] else 200

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)


@router.post("/sync/controle-contabil")
async def sync_controle_contabil(
    file: UploadFile = File(..., description="Planilha Controle Contábil (.xlsx) enviada pelo n8n"),
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """Dispatches the Controle Contábil spreadsheet ingestion.

    Accepts an uploaded Excel (.xlsx) file representing the accounting spreadsheet.
    The file is read in memory, parsed, normalized into Pandas DataFrames, and matched
    against existing database records.

    Args:
        file (UploadFile): The uploaded Excel file (.xlsx) from multipart/form-data.
        dry_run (bool): If True, processes the spreadsheet but does not write to the database.
        x_internal_token (str | None): Header token to authorize the request.

    Returns:
        JSONResponse: Ingestion statistics including records successfully synced, items
            flagged for manual review, and details of any errors encountered.
    """
    _check_token(x_internal_token)

    conteudo = await file.read()
    logger.info("Iniciando sync Controle Contábil (dry_run=%s, %d bytes)", dry_run, len(conteudo))
    resultado = run_sync_contabil(source=conteudo, dry_run=dry_run)
    logger.info("Sync contábil concluído: %s", {k: v for k, v in resultado.items() if k != "para_revisao"})

    status_code = 207 if resultado["erros"] else 200

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)

