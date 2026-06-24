"""Data models and schemas for the PAPE application.

This module defines Pydantic schemas used for request validation, response serialization,
and data transfer objects across the API, including project, member, coordination,
service, and form submission schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import date


class Projeto(BaseModel):
    """Pydantic model representing a detailed project view.

    Attributes:
        id (int): Unique identifier of the project.
        nome (str): The name of the project.
        numero_contrato (Optional[str]): Contract number linked to the project.
        valor_total (Optional[float]): Total monetary value of the contract.
        possui_orientador (Optional[bool]): Flag indicating if the project has a technical advisor.
        nome_orientador (Optional[str]): Name of the technical advisor, if applicable.
        status (Literal['ativo', 'finalizado', 'pausado']): Current lifecycle status of the project.
    """
    id: int
    nome: str
    numero_contrato: Optional[str] = None
    valor_total: Optional[float] = None
    possui_orientador: Optional[bool] = None
    nome_orientador: Optional[str] = None
    status: Literal['ativo', 'finalizado', 'pausado'] = 'ativo'


class ProjetoListItem(BaseModel):
    """Pydantic model representing a project in list views.

    Attributes:
        id (int): Unique identifier of the project.
        nome (str): Name of the project.
        numero_contrato (Optional[str]): Contract number, sanitized to omit temporary contracts.
        gerente (Optional[str]): Name of the project manager, or 'Sem gerente'.
        status (Literal['ativo', 'finalizado', 'pausado']): Current lifecycle status of the project.
    """
    id: int
    nome: str
    numero_contrato: Optional[str] = None
    gerente: Optional[str] = None
    status: Literal['ativo', 'finalizado', 'pausado']


class Coordenacao(BaseModel):
    """Pydantic model representing a department coordination unit.

    Attributes:
        id (int): Unique identifier of the coordination.
        nome (str): Name of the coordination.
    """
    id: int
    nome: str


class Servico(BaseModel):
    """Pydantic model representing a service catalog item.

    Attributes:
        id (int): Unique identifier of the service.
        nome (str): Name of the service.
        sigla (str): Service abbreviation or acronym.
    """
    id: int
    nome: str
    sigla: str


class ServicosPorCoordenacao(BaseModel):
    """Pydantic model grouping services under their respective coordination.

    Attributes:
        coordenacao_id (int): Unique identifier of the parent coordination.
        coordenacao_nome (str): Name of the coordination.
        coordenacao_sigla (str): Abbreviation of the coordination.
        servicos (list[Servico]): List of services belonging to this coordination.
    """
    coordenacao_id: int
    coordenacao_nome: str
    coordenacao_sigla: str
    servicos: list[Servico]


class Membro(BaseModel):
    """Pydantic model representing a team member.

    Attributes:
        id (int): Unique identifier of the member.
        nome (str): Full name of the member.
        email (str): Email address of the member.
    """
    id: int
    nome: str
    email: str


class MembrosPorCoordenacao(BaseModel):
    """Pydantic model grouping members under their respective coordination.

    Attributes:
        coordenacao_id (int): Unique identifier of the coordination (0 for Outros/None).
        coordenacao_nome (str): Name of the coordination department.
        coordenacao_sigla (str): Abbreviation of the coordination department.
        membros (list[Membro]): List of members linked to this coordination.
    """
    coordenacao_id: int
    coordenacao_nome: str
    coordenacao_sigla: str
    membros: list[Membro]


class PapeFormData(BaseModel):
    """Pydantic model representing the PAPE monitoring form submission.

    This schema validates responses from project managers on status, methodology,
    client relationship, budget sufficiency, technical advisory, and delays.

    Attributes:
        respondente_nome (str): Name of the project manager filling the form.
        projeto_externo_id (int): ID of the project being reported.
        primeira_resposta (Literal['Sim', 'Não']): Flag if this is the first submission for the project.
        descricao_projeto (Optional[str]): Project description (provided on first submission).
        data_inicio (Optional[str]): Start date (provided on first submission).
        numero_contrato (Optional[str]): Contract number (provided on first submission).
        valor_projeto (Optional[str]): Contract value (provided on first submission).
        servicos_projeto (Optional[str]): Comma-separated or serialized service IDs.
        coordenacoes (Optional[List[int]]): Coordination IDs involved in the project.
        possui_orientador (Literal['Sim', 'Não']): Technical advisor presence.
        nome_orientador (Optional[str]): Name of the technical advisor.
        efetividade_orientador (Optional[int]): Advisor effectiveness score (1-5).
        disponibilidade_orientador (Optional[int]): Advisor availability score (1-5).
        modelo_gerenciamento (Literal['Tradicional', 'Ágil', 'Híbrido']): Project management methodology.
        pct_story_points (Optional[str]): Percentage of story points completed (Agile only).
        houve_impedimentos (Optional[Literal['Sim', 'Não']]): Indicates if there were sprint impediments.
        tipos_impedimentos (Optional[List[str]]): Types of sprint impediments.
        cliente_percebeu_valor (Optional[int]): Score of client value perception (1-5).
        pct_marcos_prazo (Optional[str]): Percentage of milestones met on time.
        variacao_escopo (Optional[int]): Scope variation score (1-5).
        pct_conclusao (str): Project conclusion range (e.g. '0-20%').
        status_cronograma (str): Schedule status (e.g. 'Atrasado', 'Dentro do prazo').
        motivos_atraso (Optional[List[str]]): List of reasons for any delays.
        impacto_cliente (Optional[str]): Description of the impact on the client.
        capacitacao_equipe (int): Team technical capacity score (1-5).
        eficacia_metodologia (int): Management methodology effectiveness score (1-5).
        nivel_retrabalho (int): Retrabalho score (1-5).
        comunicacao_cliente (int): Client communication quality score (1-5).
        abertura_cliente (int): Client trust and openness score (1-5).
        satisfacao_cliente (int): Client satisfaction score (1-5).
        suficiencia_orcamento (Optional[Literal[1, 2, 3, 4, 5, 'Não necessitou']]): Budget sufficiency score or option.
    """
    respondente_nome: str
    projeto_externo_id: int
    primeira_resposta: Literal['Sim', 'Não']
    descricao_projeto: Optional[str] = None
    data_inicio: Optional[str] = None
    numero_contrato: Optional[str] = None
    valor_projeto: Optional[str] = None
    servicos_projeto: Optional[str] = None
    coordenacoes: Optional[List[int]] = None
    possui_orientador: Literal['Sim', 'Não']
    nome_orientador: Optional[str] = None
    efetividade_orientador: Optional[int] = Field(None, ge=1, le=5)
    disponibilidade_orientador: Optional[int] = Field(None, ge=1, le=5)
    modelo_gerenciamento: Literal['Tradicional', 'Ágil', 'Híbrido']
    pct_story_points: Optional[str] = None
    houve_impedimentos: Optional[Literal['Sim', 'Não']] = None
    tipos_impedimentos: Optional[List[str]] = None
    cliente_percebeu_valor: Optional[int] = Field(None, ge=1, le=5)
    pct_marcos_prazo: Optional[str] = None
    variacao_escopo: Optional[int] = Field(None, ge=1, le=5)
    pct_conclusao: str
    status_cronograma: str
    motivos_atraso: Optional[List[str]] = None
    impacto_cliente: Optional[str] = None
    capacitacao_equipe: int = Field(..., ge=1, le=5)
    eficacia_metodologia: int = Field(..., ge=1, le=5)
    nivel_retrabalho: int = Field(..., ge=1, le=5)
    comunicacao_cliente: int = Field(..., ge=1, le=5)
    abertura_cliente: int = Field(..., ge=1, le=5)
    satisfacao_cliente: int = Field(..., ge=1, le=5)
    suficiencia_orcamento: Optional[Literal[1, 2, 3, 4, 5, 'Não necessitou']] = None


class ProjetoUpdate(BaseModel):
    """Pydantic model for validating project updates.

    Attributes:
        nome (str): Updated project name.
        descricao_projeto (Optional[str]): Updated project description.
        data_inicio (Optional[str]): Updated start date.
        numero_contrato (Optional[str]): Updated contract number.
        valor_total (Optional[float]): Updated contract total value.
        possui_orientador (Optional[int]): Advisor status (1 for Yes, 0 for No).
        nome_orientador (Optional[str]): Updated technical advisor name.
        status (Optional[Literal['ativo', 'finalizado', 'pausado']]): Project lifecycle status.
        servicos_projeto (Optional[List[int]]): List of service IDs linked to the project.
        membros_projeto (Optional[List[str]]): Member coordination keys in "membroId-coordenacaoId" format.
        gerente_projeto (Optional[str]): Name of the new project manager.
    """
    nome: str
    descricao_projeto: Optional[str] = None
    data_inicio: Optional[str] = None
    numero_contrato: Optional[str] = None
    valor_total: Optional[float] = None
    possui_orientador: Optional[int] = None
    nome_orientador: Optional[str] = None
    status: Optional[Literal['ativo', 'finalizado', 'pausado']] = None
    servicos_projeto: Optional[List[int]] = None
    membros_projeto: Optional[List[str]] = None  # chaves "membroId-coordenacaoId"
    gerente_projeto: Optional[str] = None  # Nome do novo gerente


class ProjetoCreate(BaseModel):
    """Pydantic model for validating new project creation requests.

    Attributes:
        nome_projeto (str): Name of the new project.
        descricao_projeto (Optional[str]): Project description.
        data_inicio (Optional[str]): Project start date.
        numero_contrato (Optional[str]): Contract number.
        valor_projeto (Optional[str]): Formatted contract value string.
        servicos_projeto (Optional[List[int]]): List of service IDs to associate.
        membros_projeto (Optional[List[str]]): List of members to associate in "membroId-coordenacaoId" format.
        gerente_projeto (Optional[str]): Name of the project manager.
        possui_orientador (Literal['Sim', 'Não']): Technical advisor presence.
        nome_orientador (Optional[str]): Technical advisor name, if any.
    """
    nome_projeto: str
    descricao_projeto: Optional[str] = None
    data_inicio: Optional[str] = None
    numero_contrato: Optional[str] = None
    valor_projeto: Optional[str] = None
    servicos_projeto: Optional[List[int]] = None
    membros_projeto: Optional[List[str]] = None  # chaves "membroId-coordenacaoId"
    gerente_projeto: Optional[str] = None
    possui_orientador: Literal['Sim', 'Não'] = 'Não'
    nome_orientador: Optional[str] = None

