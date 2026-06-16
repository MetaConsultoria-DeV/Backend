"""load.py — Upserts ON DUPLICATE KEY nas 5 tabelas comerciais, na ordem das FKs.

Ordem: dim_lead_origem / dim_motivo_perda → leads → oportunidade →
oportunidade_phase_history. cliente NÃO é tocado (oportunidade.cliente_id fica NULL).
"""

import logging
from database import execute_query, execute_insert

logger = logging.getLogger("ingestion.pipefy_comercial.load")


# ── Dimensões (raw → canonical NULL, auto-vivify) ────────────────────────────

def upsert_dim_origem(source_field: str, raw_value: str) -> tuple[int, bool]:
    """Garante a origem (source_field, raw_value) em dim_lead_origem.
    Retorna (id, is_new). NUNCA toca canonical_value (Davi mapeia à mão)."""
    row = execute_query(
        "SELECT id FROM dim_lead_origem WHERE source_field = %s AND raw_value = %s LIMIT 1",
        (source_field, raw_value), fetch_one=True
    )
    if row:
        return row["id"], False
    new_id = execute_insert(
        "INSERT INTO dim_lead_origem (raw_value, source_field) VALUES (%s, %s)",
        (raw_value, source_field),
    )
    return new_id, True


def upsert_dim_motivo(source_field: str, raw_value: str) -> tuple[int, bool]:
    """Garante o motivo (source_field, raw_value) em dim_motivo_perda.
    Retorna (id, is_new). NUNCA toca canonical_value."""
    row = execute_query(
        "SELECT id FROM dim_motivo_perda WHERE source_field = %s AND raw_value = %s LIMIT 1",
        (source_field, raw_value), fetch_one=True
    )
    if row:
        return row["id"], False
    new_id = execute_insert(
        "INSERT INTO dim_motivo_perda (raw_value, source_field) VALUES (%s, %s)",
        (raw_value, source_field),
    )
    return new_id, True


# ── leads ────────────────────────────────────────────────────────────────────

def upsert_lead(lead: dict) -> int:
    """Upsert por (external_source, external_id). COALESCE para não apagar
    campos já preenchidos. Retorna o id."""
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


# ── oportunidade ─────────────────────────────────────────────────────────────

def upsert_oportunidade(o: dict) -> tuple[int, bool]:
    """Upsert por (external_source, external_id). Retorna (id, inserido).
    (rowcount do MySQL: 1=insert, 2=update, 0=update sem mudança.)"""
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


# ── oportunidade_phase_history (append-only, idempotente) ────────────────────

def upsert_phase_event(e: dict) -> bool:
    """Upsert por (external_source, external_event_id). Retorna is_new."""
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


# ── delete (card excluído no Pipefy) ─────────────────────────────────────────

def delete_oportunidade_by_external(external_source: str, external_id: str) -> int:
    """Remove a oportunidade pelo (external_source, external_id). O histórico de
    fases sai junto (FK oportunidade_phase_history ON DELETE CASCADE). leads e
    cliente NÃO são tocados. Retorna nº de linhas removidas (0 se já não existia)."""
    return execute_query(
        "DELETE FROM oportunidade WHERE external_source = %s AND external_id = %s",
        (external_source, external_id),
    )
