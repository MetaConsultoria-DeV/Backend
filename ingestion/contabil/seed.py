"""Module for deriving transaction categories from raw transaction lists.

Analyst-defined categories are extracted dynamically and consolidated. Variations in spelling,
casing, or accents are normalized to avoid duplicate database entries. Association rules
for transaction type and cell are inferred from transaction frequencies.
"""

from collections import Counter

from .normalize import norm_key


def derive_categorias(transformed: list[dict]) -> list[dict]:
    """Derives and groups database categories from transformed transactions.

    Processes transformed transaction records, grouping together items that share the same
    normalized comparison key. Resolves spelling inconsistencies by choosing the most frequent casing,
    consolidates transaction types (labeling as 'ambos' if mixed), and associates the category
    with the cell/business unit that uses it most frequently.

    Args:
        transformed (list[dict]): Transformed transaction records, each containing:
            - categoria_nome (str | None): Raw name of the transaction category.
            - tipo (str | None): Parsed direction ('entrada' or 'saida').
            - celula_nome (str | None): Canonical name of the cell, if resolved.

    Returns:
        list[dict]: A sorted list of derived category dictionaries, each containing:
            - nome (str): The canonical (most frequent) name of the category.
            - tipo (str): 'entrada', 'saida', or 'ambos'.
            - celula_nome (str | None): The canonical cell name associated with this category.
    """
    grupos: dict[str, dict] = {}
    for t in transformed:
        nome = t.get("categoria_nome")
        if not nome:
            # Transactions with missing categories are skipped here (category_id will remain NULL)
            continue
        k = norm_key(nome)
        
        # Initialize grouping data structure if key is seen for the first time
        g = grupos.setdefault(k, {"nomes": Counter(), "tipos": set(), "celulas": Counter()})
        
        # Increment frequency of specific casing/spelling variation
        g["nomes"][nome] += 1
        if t.get("tipo"):
            g["tipos"].add(t["tipo"])
        if t.get("celula_nome"):
            g["celulas"][t["celula_nome"]] += 1

    categorias = []
    for g in grupos.values():
        # Pick the most common casing/spelling variant as the canonical name
        nome = g["nomes"].most_common(1)[0][0]
        tipos = g["tipos"]
        
        # Determine canonical type based on set size and values
        if tipos == {"entrada"}:
            tipo = "entrada"
        elif tipos == {"saida"}:
            tipo = "saida"
        else:
            tipo = "ambos"  # Mixed or undefined type across transactions
            
        # Associate category with the cell that uses it most often
        celula_nome = g["celulas"].most_common(1)[0][0] if g["celulas"] else None
        categorias.append({"nome": nome, "tipo": tipo, "celula_nome": celula_nome})

    # Sort categories alphabetically for stability
    categorias.sort(key=lambda c: c["nome"].lower())
    return categorias

