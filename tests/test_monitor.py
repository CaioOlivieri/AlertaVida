"""Testes de montar_alerta (ingestão + mapeamento CEMADEN)."""

from monitor import montar_alerta


def test_montar_alerta_mapeia_nomes_padrao_cemaden():
    item = {
        "codigoalerta": 12345,
        "municipio": "Rio de Janeiro",
        "estado": "RJ",
        "tipoevento": "Alagamento",
        "nivel": "MODERADO",
        "datahoracriacao": "2025-12-20T14:30:00",
    }
    out = montar_alerta(item)
    assert out is not None
    assert out["cod_alerta"] == 12345
    assert out["municipio"] == "Rio de Janeiro"
    assert out["uf"] == "RJ"
    assert out["evento"] == "Alagamento"
    assert out["nivel"] == "MODERADO"
    assert out["datahoracriacao"] == "2025-12-20T14:30:00"


def test_montar_alerta_mapeia_nomes_alternativos_cidade_estado_tipo_evento():
    item = {
        "cod_alerta": 99,
        "cidade": "Curitiba",
        "estado": "PR",
        "tipo_evento": "Deslizamento",
        "nivel": "ALTO",
        "data_criacao": "2024-11-01 08:00:00",
    }
    out = montar_alerta(item)
    assert out is not None
    assert out["cod_alerta"] == 99
    assert out["municipio"] == "Curitiba"
    assert out["uf"] == "PR"
    assert out["evento"] == "Deslizamento"
    assert out["nivel"] == "ALTO"
    assert out["datahoracriacao"] == "2024-11-01 08:00:00"


def test_montar_alerta_retorna_none_sem_cod_alerta():
    item = {
        "municipio": "X",
        "uf": "SP",
    }
    assert montar_alerta(item) is None


def test_montar_alerta_retorna_none_quando_cod_nao_e_inteiro():
    item = {
        "cod_alerta": "nao_e_numero",
        "municipio": "X",
    }
    assert montar_alerta(item) is None


def test_montar_alerta_preenche_na_quando_campos_opcionais_ausentes():
    item = {"id": 7}
    out = montar_alerta(item)
    assert out is not None
    assert out["cod_alerta"] == 7
    for key in ("municipio", "uf", "evento", "nivel", "datahoracriacao"):
        assert out[key] == "N/A"


def test_montar_alerta_retorna_none_se_item_nao_e_dict():
    assert montar_alerta([]) is None
    assert montar_alerta("x") is None
