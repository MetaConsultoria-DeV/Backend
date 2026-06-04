"""seed.py — Deriva as categorias de `categoria_transacao` a partir das transações.

Decisão fechada: auto-seed normalizado da coluna Categoria. Categorias iguais a menos de
espaço/caixa/acentos são fundidas (mesma `norm_key`); o `tipo` e a célula são inferidos
das transações onde a categoria aparece.
"""

from collections import Counter

from .normalize import norm_key


def derive_categorias(transformed: list[dict]) -> list[dict]:
    """Recebe as linhas já transformadas e devolve a lista de categorias a semear:
    [{ "nome", "tipo": entrada|saida|ambos, "celula_nome": str|None }].
    Linhas sem categoria são ignoradas aqui (a transação fica com categoria_id NULL).
    """
    grupos: dict[str, dict] = {}
    for t in transformed:
        nome = t.get("categoria_nome")
        if not nome:
            continue
        k = norm_key(nome)
        g = grupos.setdefault(k, {"nomes": Counter(), "tipos": set(), "celulas": Counter()})
        g["nomes"][nome] += 1
        if t.get("tipo"):
            g["tipos"].add(t["tipo"])
        if t.get("celula_nome"):
            g["celulas"][t["celula_nome"]] += 1

    categorias = []
    for g in grupos.values():
        nome = g["nomes"].most_common(1)[0][0]  # forma mais frequente
        tipos = g["tipos"]
        if tipos == {"entrada"}:
            tipo = "entrada"
        elif tipos == {"saida"}:
            tipo = "saida"
        else:
            tipo = "ambos"  # mistura ou indefinido
        celula_nome = g["celulas"].most_common(1)[0][0] if g["celulas"] else None
        categorias.append({"nome": nome, "tipo": tipo, "celula_nome": celula_nome})

    categorias.sort(key=lambda c: c["nome"].lower())
    return categorias
