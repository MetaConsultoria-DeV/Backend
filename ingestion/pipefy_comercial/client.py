"""Module containing the Pipefy API client for the sales pipeline (Comercial).

Handles authentication with Pipefy via bearer token, builds headers, and executes GraphQL
queries. Supports both paginated batch retrieval (`fetch_all_cards`) and single card retrieval
(`fetch_card_by_id`) for webhook-based incremental updates.
"""

import os
import logging
import httpx
from typing import Generator

from .field_map import PIPE_ID

# Logger instance for the Pipefy Comercial client
logger = logging.getLogger("ingestion.pipefy_comercial.client")

# The endpoint for the Pipefy GraphQL API
PIPEFY_API_URL = "https://api.pipefy.com/graphql"
_TOKEN = None


def _get_token() -> str:
    """Retrieves and sanitizes the Pipefy API token from environment variables.

    Caches the token in a global variable for subsequent requests.

    Returns:
        str: The sanitized Pipefy authorization token.

    Raises:
        RuntimeError: If PIPEFY_TOKEN is not defined in the environment.
    """
    global _TOKEN
    if _TOKEN is None:
        raw = os.environ.get("PIPEFY_TOKEN", "")
        if not raw:
            raise RuntimeError("PIPEFY_TOKEN não definido no .env")
        _TOKEN = raw.removeprefix("Bearer ").strip()
    return _TOKEN


def _headers() -> dict:
    """Constructs the standard request headers for the Pipefy API.

    Returns:
        dict: Headers containing Content-Type and Authorization Bearer token.
    """
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_get_token()}",
    }


# Share GraphQL field selections between full page sync and single card queries.
# Ensures both paths return matching dict structures for the transformation stage.
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
    """Generator function that yields cards from the Sales Pipe, handling pagination automatically.

    Sends POST requests containing the GraphQL query. Uses a cursor to iterate through pages
    of 50 cards until no more pages remain.

    Args:
        pipe_id (str): The ID of the target Pipefy pipe. Defaults to PIPE_ID.

    Yields:
        dict: The dictionary representation of a single Pipefy card's node data.

    Raises:
        RuntimeError: If the GraphQL response contains errors or if network request fails.
    """
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
    """Retrieves a single card by its unique ID for incremental webhook ingestion.

    Returns the card node in the same format as fetch_all_cards, or None if the card
    no longer exists in Pipefy (e.g. if deleted between webhook dispatch and API call).

    Args:
        card_id (str): The unique identifier of the target card.

    Returns:
        dict | None: The card dictionary if found, or None if it does not exist.

    Raises:
        RuntimeError: If the GraphQL response contains application-level errors.
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

