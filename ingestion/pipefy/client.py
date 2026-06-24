"""Module containing the Pipefy API client for the finance pipeline.

Handles authentication with Pipefy via bearer token, builds headers, and executes paginated
GraphQL queries to extract card details including custom fields and phase histories.
"""

import os
import logging
import httpx
from typing import Generator

from .field_map import PIPE_ID

# Logger instance for the Pipefy client
logger = logging.getLogger("ingestion.pipefy.client")

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
        # Ensure the token has the "Bearer " prefix removed before storing
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


# GraphQL query to retrieve pages of cards within a pipe.
# Fetches card details, custom field values, and phase transition logs.
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
    """Generator function that yields cards from Pipefy, handling pagination automatically.

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
    # Use httpx Client to keep connection open across pages
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

            # Handle application-level errors returned in the GraphQL body
            if "errors" in body:
                raise RuntimeError(f"Pipefy GraphQL errors: {body['errors']}")

            data = body["data"]["allCards"]
            edges = data["edges"]
            logger.info("Página %d: %d cards", page, len(edges))

            for edge in edges:
                yield edge["node"]

            page_info = data["pageInfo"]
            # Stop paginating when hasNextPage is False
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]

