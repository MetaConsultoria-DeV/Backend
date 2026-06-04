"""parser.py — Lê o .xlsx do Controle Contábil e devolve linhas cruas da tabela.

A planilha tem o cabeçalho 'Data | Conta | Entrada/Saída | Setor | Categoria | Nº do
Projeto | Valor | Observações' DUAS vezes; a tabela válida é a que é seguida por linhas
com data de verdade. O parser ancora por rótulo (não por número de linha fixo), porque as
analistas inserem linhas.
"""

import io
import logging
import datetime as _dt
from typing import Optional, Union

import openpyxl

from .normalize import norm_key

logger = logging.getLogger("ingestion.contabil.parser")

# Colunas da tabela (0-based): D..K
COL_DATA = 3
COL_CONTA = 4
COL_TIPO = 5
COL_SETOR = 6
COL_CATEGORIA = 7
COL_PROJETO = 8
COL_VALOR = 9
COL_OBS = 10


def _is_header_row(row: tuple) -> bool:
    """Heurística: a linha tem 'data' em D, 'conta' em E e 'valor' em J."""
    def at(i):
        return norm_key(row[i]) if i < len(row) and row[i] is not None else ""
    return at(COL_DATA).startswith("data") and at(COL_CONTA).startswith("conta") \
        and at(COL_VALOR).startswith("valor")


def _as_date(value) -> Optional[_dt.date]:
    """Converte a célula de data para date; None se não for uma data de verdade.

    datetime.time (rodapé, célula vazia formatada) NÃO é data — vira None.
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return None


def parse_xlsx(source: Union[bytes, str, io.BytesIO]) -> list[dict]:
    """Recebe os bytes do .xlsx (upload do n8n) OU um caminho de arquivo (testes).

    Devolve uma lista de dicts crus — só as linhas que têm data de verdade (transações).
    Cabeçalhos, painéis laterais, totais e rodapés ficam de fora.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))

    # Acha a linha de cabeçalho válida: um cabeçalho seguido por uma linha com data real.
    header_idx = None
    for i, row in enumerate(rows):
        if _is_header_row(row):
            nxt = rows[i + 1] if i + 1 < len(rows) else ()
            if nxt and len(nxt) > COL_DATA and _as_date(nxt[COL_DATA]) is not None:
                header_idx = i
                break
    if header_idx is None:
        # fallback: última ocorrência de cabeçalho, mesmo sem data logo abaixo
        candidatos = [i for i, row in enumerate(rows) if _is_header_row(row)]
        if not candidatos:
            raise ValueError("Cabeçalho da tabela de transações não encontrado na planilha")
        header_idx = candidatos[-1]
        logger.warning("Cabeçalho achado por fallback na linha %d", header_idx + 1)

    out: list[dict] = []
    for i in range(header_idx + 1, len(rows)):
        row = rows[i]
        if row is None:
            continue
        data = _as_date(row[COL_DATA] if len(row) > COL_DATA else None)
        if data is None:
            # linha sem data não é transação (total, rodapé, separador) — descartar
            continue

        def cell(idx):
            return row[idx] if len(row) > idx else None

        out.append({
            "row_num": i + 1,  # 1-based, para mensagens de revisão
            "data": data,
            "conta": cell(COL_CONTA),
            "tipo": cell(COL_TIPO),
            "setor": cell(COL_SETOR),
            "categoria": cell(COL_CATEGORIA),
            "projeto": cell(COL_PROJETO),
            "valor": cell(COL_VALOR),
            "obs": cell(COL_OBS),
        })

    wb.close()
    logger.info("Planilha lida: %d transações (cabeçalho na linha %d)", len(out), header_idx + 1)
    return out
