"""client.py — Chamadas GraphQL paginadas ao Pipefy de Vendas (Sales Pipeline)."""

import os
import logging
import httpx
from typing import Generator

from .field_map import PIPE_ID

logger = logging.getLogger("ingestion.pipefy_comercial.client")

PIPEFY_API_URL = "https://api.pipefy.com/graphql"
_TOKEN = None


def _get_token() -> str:
    global _TOKEN
    if _TOKEN is None:
        raw = os.environ.get("PIPEFY_TOKEN", "")
        if not raw:
            raise RuntimeError("PIPEFY_TOKEN não definido no .env")
        _TOKEN = raw.removeprefix("Bearer ").strip()
    return _TOKEN


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_get_token()}",
    }


# Seleção compartilhada entre a query paginada (allCards) e a de card único (card),
# pra que os dois caminhos retornem a MESMA estrutura que transform_card espera.
# Inclui labels do card (etiqueta de coordenação) e phases_history (funil/duração).
_CARD_NODE_FIELDS = """
    id
    title
    current_phase { id name }
    createdAt
    finished_at
    labels { name }
    fields {
      name
      value
      array_value
      field { id type }
    }
    phases_history {
      phase { id name }
      firstTimeIn
      lastTimeOut
      duration
    }
"""

_CARDS_QUERY = """
query ($pipeId: ID!, $cursor: String) {
  allCards(pipeId: $pipeId, first: 50, after: $cursor) {
    edges {
      node {%s}
    }
    pageInfo { hasNextPage endCursor }
  }
}
""" % _CARD_NODE_FIELDS

_CARD_QUERY = """
query ($cardId: ID!) {
  card(id: $cardId) {%s}
}
""" % _CARD_NODE_FIELDS


def fetch_all_cards(pipe_id: str = PIPE_ID) -> Generator[dict, None, None]:
    """Gera um card por vez, paginando automaticamente."""
    cursor = None
    page = 0
    with httpx.Client(timeout=60) as http:
        while True:
            page += 1
            variables = {"pipeId": pipe_id, "cursor": cursor}
            resp = http.post(
                PIPEFY_API_URL,
                headers=_headers(),
                json={"query": _CARDS_QUERY, "variables": variables},
            )
            resp.raise_for_status()
            body = resp.json()

            if "errors" in body:
                raise RuntimeError(f"Pipefy GraphQL errors: {body['errors']}")

            data = body["data"]["allCards"]
            edges = data["edges"]
            logger.info("Página %d: %d cards", page, len(edges))

            for edge in edges:
                yield edge["node"]

            page_info = data["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]


def fetch_card_by_id(card_id: str) -> dict | None:
    """Busca um único card pelo id (ingestão incremental via webhook).

    Retorna o node no mesmo formato de fetch_all_cards, ou None se o card não
    existir mais no Pipefy (ex.: deletado entre o evento e a chamada).
    """
    with httpx.Client(timeout=60) as http:
        resp = http.post(
            PIPEFY_API_URL,
            headers=_headers(),
            json={"query": _CARD_QUERY, "variables": {"cardId": card_id}},
        )
        resp.raise_for_status()
        body = resp.json()

        if "errors" in body:
            raise RuntimeError(f"Pipefy GraphQL errors: {body['errors']}")

        return body["data"]["card"]
