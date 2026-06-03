"""router.py — POST /internal/sync/pipefy-financeiro"""

import os
import logging
from fastapi import APIRouter, Header, HTTPException, Query

from .pipefy.sync import run_sync

logger = logging.getLogger("ingestion.router")
router = APIRouter(prefix="/internal", tags=["internal"])

_INTERNAL_TOKEN: str = os.getenv("INTERNAL_SYNC_TOKEN", "")


def _check_token(x_internal_token: str | None) -> None:
    if not _INTERNAL_TOKEN:
        raise HTTPException(status_code=500, detail="INTERNAL_SYNC_TOKEN não configurado")
    if x_internal_token != _INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Token interno inválido ou ausente")


@router.post("/sync/pipefy-financeiro")
def sync_pipefy_financeiro(
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """
    Dispara a sincronização Pipefy Financeiro → MySQL.

    - Exige header `X-Internal-Token` igual a `INTERNAL_SYNC_TOKEN` no .env.
    - `?dry_run=true` roda tudo sem gravar (ideal para validação).
    """
    _check_token(x_internal_token)

    logger.info("Iniciando sync Pipefy Financeiro (dry_run=%s)", dry_run)
    resultado = run_sync(dry_run=dry_run)
    logger.info("Sync concluído: %s", resultado)

    status_code = 200
    if resultado["erros"]:
        status_code = 207  # Multi-Status — parcialmente bem-sucedido

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)
