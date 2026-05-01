"""Testes de montar_alerta (ingestão + mapeamento CEMADEN)."""

import pytest
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from alertavida.monitor import fetch_alertas_com_retry, montar_alerta


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
    assert out.cod_alerta == 12345
    assert out.municipio.nome == "Rio de Janeiro"
    assert out.municipio.uf == "RJ"
    assert out.tipo_evento.value == "HIDROLOGICO"
    assert out.nivel_risco.value == "MODERADO"
    assert out.data_criacao == datetime(2025, 12, 20, 14, 30, tzinfo=timezone.utc)


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
    assert out.cod_alerta == 99
    assert out.municipio.nome == "Curitiba"
    assert out.municipio.uf == "PR"
    assert out.tipo_evento.value == "GEOLOGICO"
    assert out.nivel_risco.value == "ALTO"
    assert out.data_criacao == datetime(2024, 11, 1, 8, 0, tzinfo=timezone.utc)


def test_montar_alerta_retorna_none_sem_cod_alerta():
    item = {
        "municipio": "X",
        "uf": "SP",
    }
    with pytest.raises(ValueError):
        montar_alerta(item)


def test_montar_alerta_retorna_none_quando_cod_nao_e_inteiro():
    item = {
        "cod_alerta": "nao_e_numero",
        "municipio": "X",
    }
    with pytest.raises(ValueError):
        montar_alerta(item)


def test_montar_alerta_preenche_na_quando_campos_opcionais_ausentes():
    item = {"id": 7}
    with pytest.raises(ValueError):
        montar_alerta(item)


def test_montar_alerta_retorna_none_se_item_nao_e_dict():
    with pytest.raises(ValueError):
        montar_alerta([])
    with pytest.raises(ValueError):
        montar_alerta("x")


def test_montar_alerta_retorna_none_quando_item_e_none():
    with pytest.raises(ValueError):
        montar_alerta(None)


def test_fetch_sucesso_primeira_tentativa():
    payload = b'{"ok": true}'
    response = Mock()
    response.read.return_value = payload
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)

    with patch("alertavida.monitor.urlopen", return_value=context) as mock_urlopen:
        with patch("alertavida.monitor.time.sleep") as mock_sleep:
            out = fetch_alertas_com_retry("https://exemplo")

    assert out == payload
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_sucesso_apos_falhas_temporarias():
    payload = b"ok"
    response = Mock()
    response.read.return_value = payload
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)

    with patch(
        "alertavida.monitor.urlopen",
        side_effect=[URLError("timeout"), URLError("conexao"), context],
    ) as mock_urlopen:
        with patch("alertavida.monitor.time.sleep") as mock_sleep:
            out = fetch_alertas_com_retry("https://exemplo")

    assert out == payload
    assert mock_urlopen.call_count == 3
    assert mock_sleep.call_count == 2


def test_fetch_falha_4xx_nao_faz_retry():
    err = HTTPError(
        url="https://exemplo",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )
    with patch("alertavida.monitor.urlopen", side_effect=err) as mock_urlopen:
        with patch("alertavida.monitor.time.sleep") as mock_sleep:
            try:
                fetch_alertas_com_retry("https://exemplo")
                assert False, "Era esperado HTTPError(404)"
            except HTTPError as exc:
                assert exc.code == 404

    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_esgota_tentativas_e_propaga():
    with patch("alertavida.monitor.urlopen", side_effect=URLError("falha")) as mock_urlopen:
        with patch("alertavida.monitor.time.sleep") as mock_sleep:
            try:
                fetch_alertas_com_retry("https://exemplo")
                assert False, "Era esperado URLError após esgotar tentativas"
            except URLError:
                pass

    assert mock_urlopen.call_count == 4
    assert mock_sleep.call_count == 3
