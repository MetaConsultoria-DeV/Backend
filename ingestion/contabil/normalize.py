"""normalize.py — Funções puras de normalização da planilha Controle Contábil.

Sem acesso a banco nem a arquivo: só transformam strings/valores conforme as regras
fechadas no `plano_ingestao_controle_contabil.md`. São o ponto mais testável do módulo.
"""

import re
import unicodedata
from typing import Optional

# external_source fixo desta fonte (bate com o DEFAULT do schema em `transacao`).
EXTERNAL_SOURCE = "sharepoint_caixa"

# Código de projeto no padrão NNN.YYYY (o mesmo do Pipefy).
_CODIGO_RE = re.compile(r"\b(\d{3}\.\d{4})\b")


def norm_text(value) -> Optional[str]:
    """Trim + colapsa espaços internos. Devolve None se ficar vazio.

    Mantém acentos e caixa — é a forma 'limpa' que vai pro banco (nome de categoria etc.).
    """
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def norm_key(value) -> str:
    """Chave de comparação: casefold + remove acentos + colapsa espaços.

    Usada para casar setores/contas/categorias sujas ('Camisas Polo ' == 'camisas polo').
    """
    s = norm_text(value)
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = nfkd.encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def parse_tipo(value) -> Optional[str]:
    """'Entrada' -> 'entrada'; 'Saída'/'Saida' -> 'saida'; resto -> None."""
    k = norm_key(value)
    if k.startswith("entrada"):
        return "entrada"
    if k.startswith("saida"):
        return "saida"
    return None


# Setor (planilha) -> nome da célula no banco. Valor None = setor reconhecido mas SEM
# célula (movimento geral/interno): celula_id fica NULL. Setor fora deste mapa não é
# reconhecido e vai para revisão.
_SETOR_TO_CELULA = {
    "presidencia": "Presidência",
    "projetos": "Projetos",
    "operacoes": "Operações",
    "gestao de pessoas": "Gestão de Pessoas",
    "marketing": "Marketing e Vendas",
    "area comercial": "Marketing e Vendas",
    "gerais": None,
}


def map_setor(value) -> tuple[Optional[str], bool]:
    """Devolve (nome_da_celula_ou_None, reconhecido).

    - ('Operações', True)  -> casa com a célula.
    - (None, True)         -> 'Gerais': reconhecido, mas celula_id NULL.
    - (None, False)        -> setor desconhecido: vai para revisão (celula_id NULL).
    """
    k = norm_key(value)
    if not k:
        return (None, False)
    if k in _SETOR_TO_CELULA:
        return (_SETOR_TO_CELULA[k], True)
    return (None, False)


def parse_valor(value) -> Optional[float]:
    """Valor sempre positivo (o sinal vive no `tipo`). Aceita número ou string com
    vírgula/R$. Devolve None se não der pra interpretar."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(abs(float(value)), 2)
    s = str(value).strip()
    s = s.replace("R$", "").replace(" ", "")
    # Formato brasileiro: 1.234,56 -> 1234.56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return round(abs(float(s)), 2)
    except ValueError:
        return None


def extract_codigo(value) -> Optional[str]:
    """Extrai NNN.YYYY da coluna 'Nº do Projeto'. Rótulos que não são código
    ('ImpulseUp', 'Reajuste de Saldo', vazio…) -> None (não é projeto)."""
    if value is None:
        return None
    m = _CODIGO_RE.search(str(value))
    return m.group(1) if m else None
