from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import date


class Projeto(BaseModel):
    id: int
    nome: str
    numero_contrato: Optional[str] = None
    valor_total: Optional[float] = None


class Coordenacao(BaseModel):
    id: int
    nome: str


class Membro(BaseModel):
    id: int
    nome: str
    email: str


class PapeFormData(BaseModel):
    # Identificação
    respondente_nome: str

    # Iniciação
    projeto_externo_id: int
    primeira_resposta: Literal['Sim', 'Não']

    # Procedimentos Iniciais (condicional)
    data_inicio: Optional[str] = None
    numero_contrato: Optional[str] = None
    valor_projeto: Optional[str] = None
    servicos_projeto: Optional[str] = None
    coordenacoes: Optional[List[int]] = None

    # Orientador Técnico
    possui_orientador: Literal['Sim', 'Não']
    nome_orientador: Optional[str] = None
    efetividade_orientador: Optional[int] = Field(None, ge=1, le=5)
    disponibilidade_orientador: Optional[int] = Field(None, ge=1, le=5)

    # Metodologia
    modelo_gerenciamento: Literal['Tradicional', 'Ágil', 'Híbrido']

    # Seção Ágil (condicional)
    pct_story_points: Optional[str] = None
    houve_impedimentos: Optional[Literal['Sim', 'Não']] = None
    tipos_impedimentos: Optional[List[str]] = None

    # Seção Tradicional/Híbrido (condicional)
    cliente_percebeu_valor: Optional[int] = Field(None, ge=1, le=5)
    pct_marcos_prazo: Optional[str] = None
    variacao_escopo: Optional[int] = Field(None, ge=1, le=5)

    # Execução e Cronograma
    pct_conclusao: str
    status_cronograma: str
    motivos_atraso: Optional[List[str]] = None
    impacto_cliente: Optional[str] = None

    # Capacidade e Planejamento
    capacitacao_equipe: int = Field(..., ge=1, le=5)
    eficacia_metodologia: int = Field(..., ge=1, le=5)
    nivel_retrabalho: int = Field(..., ge=1, le=5)

    # Comunicação e Cliente
    comunicacao_cliente: int = Field(..., ge=1, le=5)
    abertura_cliente: int = Field(..., ge=1, le=5)
    satisfacao_cliente: int = Field(..., ge=1, le=5)

    # Orçamento
    suficiencia_orcamento: Optional[Literal[1, 2, 3, 4, 5, 'Não necessitou']] = None
