"""Module for loading Pipefy Comercial (Sales Pipeline) data into the MySQL database.

Coordinates upserts across commercial schemas:
1. dim_lead_origem / dim_motivo_perda (Dimension tables with automatic value harvesting/seeding)
2. leads (Leads/prospect profiles)
3. oportunidade (Sales opportunities linked to leads and coordination)
4. oportunidade_phase_history (Phase transition event logs)

Handles deletes cascaded via foreign keys if a card is deleted in the source pipeline.
"""

import logging
from database import execute_query, execute_insert

# Logger instance for the Comercial load module
logger = logging.getLogger("ingestion.pipefy_comercial.load")


# --- Dimensions (Auto-seeding dimensions) ---

def upsert_dim_origem(source_field: str, raw_value: str) -> tuple[int, bool]:
    """Ensures a lead origin row exists in the `dim_lead_origem` table.

    Performs dynamic auto-seeding. If the raw value combined with the source field ID
    does not exist, inserts it. Does not overwrite the `canonical_value` column, as that is
    manually curated by analysts in the database.

    Args:
        source_field (str): The ID of the field that captured this value.
        raw_value (str): The raw string value captured from the source card.

    Returns:
        tuple[int, bool]: A tuple containing:
            - int: The database ID of the matched or newly inserted origin row.
            - bool: True if a new origin row was inserted, False if it already existed.
    """
    row = execute_query(
        "SELECT id FROM dim_lead_origem WHERE source_field = %s AND raw_value = %s LIMIT 1",
        (source_field, raw_value), fetch_one=True
    )
    if row:
        return row["id"], False
        
    # Insert new unmapped raw origin record
    new_id = execute_insert(
        "INSERT INTO dim_lead_origem (raw_value, source_field) VALUES (%s, %s)",
        (raw_value, source_field),
    )
    return new_id, True


def upsert_dim_motivo(source_field: str, raw_value: str) -> tuple[int, bool]:
    """Ensures a loss reason row exists in the `dim_motivo_perda` table.

    Performs dynamic auto-seeding. If the raw reason combined with the source field ID
    does not exist, inserts a new row. Leaves `canonical_value` untouched for manual curation.

    Args:
        source_field (str): The ID of the field that captured this loss reason.
        raw_value (str): The raw reason string captured from the source card.

    Returns:
        tuple[int, bool]: A tuple containing:
            - int: The database ID of the matched or newly inserted reason row.
            - bool: True if a new reason row was inserted, False if it already existed.
    """
    row = execute_query(
        "SELECT id FROM dim_motivo_perda WHERE source_field = %s AND raw_value = %s LIMIT 1",
        (source_field, raw_value), fetch_one=True
    )
    if row:
        return row["id"], False
        
    # Insert new unmapped raw loss reason record
    new_id = execute_insert(
        "INSERT INTO dim_motivo_perda (raw_value, source_field) VALUES (%s, %s)",
        (raw_value, source_field),
    )
    return new_id, True


# --- Leads ---

def upsert_lead(lead: dict) -> int:
    """Upserts a lead/prospect profile record, unique by `(external_source, external_id)`.

    Uses COALESCE to prevent overwriting existing lead details (like phone or email)
    if subsequent events omit them.

    Args:
        lead (dict): Lead fields containing:
            - nome (str): Lead contact name.
            - email (str | None): Contact email.
            - telefone (str | None): Contact phone number.
            - empresa (str | None): Company name.
            - cargo (str | None): Job title.
            - external_source (str): Source identifier (pipefy_comercial).
            - external_id (str): Unique card/lead identifier.

    Returns:
        int: The database ID of the lead.

    Raises:
        RuntimeError: If the lead cannot be fetched after the transaction.
    """
    execute_query(
        """
        INSERT INTO leads (nome, email, telefone, empresa, cargo, external_source, external_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            nome     = VALUES(nome),
            email    = COALESCE(VALUES(email), email),
            telefone = COALESCE(VALUES(telefone), telefone),
            empresa  = COALESCE(VALUES(empresa), empresa),
            cargo    = COALESCE(VALUES(cargo), cargo)
        """,
        (lead["nome"], lead.get("email"), lead.get("telefone"), lead.get("empresa"),
         lead.get("cargo"), lead["external_source"], lead["external_id"]),
    )
    row = execute_query(
        "SELECT id FROM leads WHERE external_source = %s AND external_id = %s LIMIT 1",
        (lead["external_source"], lead["external_id"]), fetch_one=True
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert lead: {lead['external_id']}")
    return row["id"]


# --- Oportunidade ---

def upsert_oportunidade(o: dict) -> tuple[int, bool]:
    """Upserts a sales opportunity record, unique by `(external_source, external_id)`.

    COALESCE is used for attributes like closed value, origin, or coordination to preserve
    manually registered or previously captured details.

    Args:
        o (dict): Opportunity fields containing:
            - lead_id (int): Foreign key referencing the lead profile.
            - cliente_id (int | None): Foreign key referencing client (usually NULL).
            - fase_atual_nome (str): Current pipeline stage name.
            - fase_atual_id (str): Current pipeline stage identifier.
            - responsaveis (str | None): Assigned negotiators list.
            - valor_fechado (float | None): Closed financial amount.
            - origem_id (int | None): Mapped lead origin reference.
            - motivo_perda_id (int | None): Mapped loss reason reference.
            - coordenacao_id (int | None): Mapped coordination reference.
            - status_terminal (str): 'ativo', 'fechado', 'desistido', etc.
            - criado_em (datetime): Creation date.
            - finalizado_em (datetime | None): Finalization timestamp.
            - external_source (str): Source system tag.
            - external_id (str): Unique opportunity identifier (card ID).

    Returns:
        tuple[int, bool]: A tuple containing:
            - int: The opportunity database ID.
            - bool: True if a new opportunity row was created (rowcount == 1), False otherwise.

    Raises:
        RuntimeError: If opportunity cannot be retrieved after database operation.
    """
    rowcount = execute_query(
        """
        INSERT INTO oportunidade (
            lead_id, cliente_id, fase_atual_nome, fase_atual_id, responsaveis,
            valor_fechado, origem_id, motivo_perda_id, coordenacao_id,
            status_terminal, criado_em, finalizado_em, external_id, external_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            lead_id         = VALUES(lead_id),
            fase_atual_nome = VALUES(fase_atual_nome),
            fase_atual_id   = VALUES(fase_atual_id),
            responsaveis    = COALESCE(VALUES(responsaveis), responsaveis),
            valor_fechado   = COALESCE(VALUES(valor_fechado), valor_fechado),
            origem_id       = COALESCE(VALUES(origem_id), origem_id),
            motivo_perda_id = COALESCE(VALUES(motivo_perda_id), motivo_perda_id),
            coordenacao_id  = COALESCE(VALUES(coordenacao_id), coordenacao_id),
            status_terminal = VALUES(status_terminal),
            finalizado_em   = COALESCE(VALUES(finalizado_em), finalizado_em)
        """,
        (
            o.get("lead_id"), o.get("cliente_id"), o["fase_atual_nome"], o["fase_atual_id"],
            o.get("responsaveis"), o.get("valor_fechado"), o.get("origem_id"),
            o.get("motivo_perda_id"), o.get("coordenacao_id"), o["status_terminal"],
            o.get("criado_em"), o.get("finalizado_em"),
            o["external_id"], o["external_source"],
        ),
    )
    row = execute_query(
        "SELECT id FROM oportunidade WHERE external_source = %s AND external_id = %s LIMIT 1",
        (o["external_source"], o["external_id"]), fetch_one=True
    )
    if not row:
        raise RuntimeError(f"Falha ao upsert oportunidade: {o['external_id']}")
    return row["id"], (rowcount == 1)


# --- Opportunity Phase History ---

def upsert_phase_event(e: dict) -> bool:
    """Inserts or updates a phase transition event log.

    Enforces uniqueness on `(external_source, external_event_id)` to prevent duplicating
    transition history records during re-sync.

    Args:
        e (dict): Event fields:
            - oportunidade_id (int): Database ID of the opportunity.
            - from_phase_id (str | None): ID of previous phase.
            - from_phase_nome (str | None): Name of previous phase.
            - to_phase_id (str): ID of new phase.
            - to_phase_nome (str): Name of new phase.
            - moved_at (datetime): Transition timestamp.
            - moved_by (str | None): User who performed the action.
            - duration_previous_phase_seconds (int | None): Seconds spent in previous phase.
            - external_event_id (str): Unique ID representing this transition event.
            - external_source (str): Source system.

    Returns:
        bool: True if the phase event was newly inserted (rowcount == 1), False if updated.
    """
    rowcount = execute_query(
        """
        INSERT INTO oportunidade_phase_history (
            oportunidade_id, from_phase_id, from_phase_nome, to_phase_id, to_phase_nome,
            moved_at, moved_by, duration_previous_phase_seconds,
            external_event_id, external_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            from_phase_id   = VALUES(from_phase_id),
            from_phase_nome = VALUES(from_phase_nome),
            duration_previous_phase_seconds = COALESCE(
                VALUES(duration_previous_phase_seconds), duration_previous_phase_seconds)
        """,
        (
            e["oportunidade_id"], e.get("from_phase_id"), e.get("from_phase_nome"),
            e["to_phase_id"], e["to_phase_nome"], e.get("moved_at"), e.get("moved_by"),
            e.get("duration_previous_phase_seconds"),
            e["external_event_id"], e["external_source"],
        ),
    )
    return rowcount == 1


# --- Delete Operations ---

def delete_oportunidade_by_external(external_source: str, external_id: str) -> int:
    """Deletes an opportunity by its external source key and ID.

    The database schema cascades deletions, meaning removing an opportunity automatically
    clears associated records in `oportunidade_phase_history`. Related profiles in `leads`
    and `cliente` tables are not deleted.

    Args:
        external_source (str): The external source key (e.g. 'pipefy_comercial').
        external_id (str): Unique card identifier.

    Returns:
        int: Number of opportunity rows deleted from the database.
    """
    return execute_query(
        "DELETE FROM oportunidade WHERE external_source = %s AND external_id = %s",
        (external_source, external_id),
    )

