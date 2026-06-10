"""router.py — POST /internal/sync/pipefy-financeiro"""

import os
import logging
import secrets
from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File

from .pipefy.sync import run_sync
from .pipefy_comercial.sync import run_sync as run_sync_comercial
from .contabil.sync import run_sync as run_sync_contabil

logger = logging.getLogger("ingestion.router")
router = APIRouter(prefix="/internal", tags=["internal"])

def _check_token(x_internal_token: str | None) -> None:
    # Lido em tempo de chamada (não no import) para não depender da ordem de load_dotenv.
    internal_token = os.getenv("INTERNAL_SYNC_TOKEN", "")
    if not internal_token:
        raise HTTPException(status_code=503, detail="INTERNAL_SYNC_TOKEN não configurado")
    # compare_digest: comparação em tempo constante (evita timing attack)
    if not x_internal_token or not secrets.compare_digest(x_internal_token, internal_token):
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


@router.post("/sync/pipefy-comercial")
def sync_pipefy_comercial(
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """
    Dispara a sincronização Pipefy de Vendas (Sales Pipeline) → MySQL comercial.

    - Exige header `X-Internal-Token` igual a `INTERNAL_SYNC_TOKEN` no .env.
    - `?dry_run=true` roda tudo sem gravar (ideal para validação).
    """
    _check_token(x_internal_token)

    logger.info("Iniciando sync Pipefy Comercial (dry_run=%s)", dry_run)
    resultado = run_sync_comercial(dry_run=dry_run)
    logger.info("Sync comercial concluído: %s", resultado)

    status_code = 207 if resultado["erros"] else 200

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)


@router.post("/sync/controle-contabil")
async def sync_controle_contabil(
    file: UploadFile = File(..., description="Planilha Controle Contábil (.xlsx) enviada pelo n8n"),
    dry_run: bool = Query(default=False, description="Se true, não grava no banco"),
    x_internal_token: str | None = Header(default=None),
):
    """
    Dispara a sincronização do Controle Contábil (planilha SharePoint) → MySQL.

    - Exige header `X-Internal-Token` igual a `INTERNAL_SYNC_TOKEN` no .env.
    - Corpo: o arquivo .xlsx (multipart form-data, campo `file`). O n8n baixa do
      SharePoint via Microsoft Graph e envia aqui — o backend não acessa o SharePoint.
    - `?dry_run=true` roda tudo sem gravar (ideal para validação).
    """
    _check_token(x_internal_token)

    conteudo = await file.read()
    logger.info("Iniciando sync Controle Contábil (dry_run=%s, %d bytes)", dry_run, len(conteudo))
    resultado = run_sync_contabil(source=conteudo, dry_run=dry_run)
    logger.info("Sync contábil concluído: %s", {k: v for k, v in resultado.items() if k != "para_revisao"})

    status_code = 207 if resultado["erros"] else 200

    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content=resultado)
