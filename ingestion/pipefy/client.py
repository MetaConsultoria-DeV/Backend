"""client.py — Chamadas GraphQL paginadas ao Pipefy Financeiro."""

import os
import logging
import httpx
from typing import Generator

from .field_map import PIPE_ID

logger = logging.getLogger("ingestion.pipefy.client")

PIPEFY_API_URL = "https://api.pipefy.com/graphql"
_TOKEN = None


def _get_token() -> str:
    global _TOKEN
    if _TOKEN is None:
        raw = os.environ.get("PIPEFY_TOKEN", "")
        if not raw:
            raise RuntimeError("PIPEFY_TOKEN não definido no .env")
        # Aceita com ou sem prefixo "Bearer "
        _TOKEN = raw.removeprefix("Bearer ").strip()
    return _TOKEN


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_get_token()}",
    }


_CARDS_QUERY = """
query ($pipeId: ID!, $cursor: String) {
  allCards(pipeId: $pipeId, first: 50, after: $cursor) {
    edges {
      node {
        id
        title
        current_phase { name }
        createdAt
        finished_at
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
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


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
