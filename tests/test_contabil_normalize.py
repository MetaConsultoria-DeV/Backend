"""Testes das normalizações do Controle Contábil (funções puras, sem banco)."""

from ingestion.contabil import normalize as N


def test_norm_text_colapsa_espaco_e_vazio():
    assert N.norm_text("  Camisas Polo  ") == "Camisas Polo"
    assert N.norm_text("a\n b") == "a b"
    assert N.norm_text("   ") is None
    assert N.norm_text(None) is None


def test_norm_key_funde_caixa_acento_espaco():
    assert N.norm_key("Camisas Polo ") == N.norm_key("camisas polo")
    assert N.norm_key("Operações") == "operacoes"
    assert N.norm_key("Gestão de Pessoas") == "gestao de pessoas"


def test_parse_tipo():
    assert N.parse_tipo("Saída") == "saida"
    assert N.parse_tipo("Saida") == "saida"
    assert N.parse_tipo("Entrada") == "entrada"
    assert N.parse_tipo("") is None
    assert N.parse_tipo(None) is None


def test_map_setor():
    assert N.map_setor("Operações ") == ("Operações", True)
    assert N.map_setor("Marketing") == ("Marketing e Vendas", True)
    assert N.map_setor("Área Comercial") == ("Marketing e Vendas", True)
    assert N.map_setor("Gerais") == (None, True)        # reconhecido, sem célula
    assert N.map_setor("Banana") == (None, False)       # desconhecido -> revisão
    assert N.map_setor(None) == (None, False)


def test_parse_valor_sempre_positivo():
    assert N.parse_valor(229.62) == 229.62
    assert N.parse_valor(-130.64) == 130.64            # sinal vive no tipo
    assert N.parse_valor("1.234,56") == 1234.56        # formato BR
    assert N.parse_valor("R$ 150") == 150.0
    assert N.parse_valor("") is None
    assert N.parse_valor(None) is None


def test_extract_codigo():
    assert N.extract_codigo("010.2026") == "010.2026"
    assert N.extract_codigo("Pacote 011.2025 algo") == "011.2025"
    assert N.extract_codigo("ImpulseUp") is None
    assert N.extract_codigo("Reajuste de Saldo") is None
    assert N.extract_codigo("") is None
    assert N.extract_codigo(None) is None
