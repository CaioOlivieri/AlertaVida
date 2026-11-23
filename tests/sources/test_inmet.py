"""Testes de InmetSource e AvisoMeteorologico (issue #153)."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from alertavida.domain.aviso import AvisoMeteorologico, SeveridadeAviso
from alertavida.sources.base import FalhaDeColeta
from alertavida.sources.inmet import InmetSource, montar_aviso

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "inmet" / "avisos_ativos_2026-11-23.json"
)
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _opener(payload: object):
    resposta = Mock()
    resposta.read.return_value = json.dumps(payload).encode("utf-8")
    contexto = Mock()
    contexto.__enter__ = Mock(return_value=resposta)
    contexto.__exit__ = Mock(return_value=False)
    return Mock(return_value=contexto)


class TestMontarAviso:
    def test_payload_real_de_2026_11_23(self):
        aviso = montar_aviso(PAYLOAD["futuro"][0])
        assert aviso.codigo_cap == "urn:oid:2.49.0.0.76.0.2026.28747.1"
        assert (aviso.id_aviso, aviso.id_sequencia) == (28747, 1)
        assert aviso.evento == "Tempestade"
        assert aviso.severidade is SeveridadeAviso.PERIGO_POTENCIAL
        assert len(aviso.codigos_ibge) == 40  # fixture recortada; o real tinha 3.206

    def test_inicio_e_horario_de_brasilia_nao_o_z_do_json(self):
        """O JSON diz `data_inicio: 2026-11-24T00:00:00.000Z`; o CAP oficial do
        mesmo aviso diz `onset 2026-11-24T00:00:00-03:00`. O coletor tem de
        concordar com o CAP: 03:00 UTC, não 00:00 UTC."""
        aviso = montar_aviso(PAYLOAD["futuro"][0])
        assert PAYLOAD["futuro"][0]["data_inicio"] == "2026-11-24T00:00:00.000Z"
        assert aviso.inicio == datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
        assert aviso.fim == datetime(2026, 11, 25, 2, 59, tzinfo=timezone.utc)

    @pytest.mark.parametrize("campo", ["codigo", "geocodes", "inicio", "severidade"])
    def test_campo_ausente_vira_value_error(self, campo):
        item = copy.deepcopy(PAYLOAD["hoje"][0])
        del item[campo]
        with pytest.raises(ValueError):
            montar_aviso(item)

    def test_severidade_desconhecida_vira_value_error(self):
        item = copy.deepcopy(PAYLOAD["hoje"][0])
        item["severidade"] = "Apocalipse"
        with pytest.raises(ValueError, match="Severidade INMET desconhecida"):
            montar_aviso(item)


class TestSeveridade:
    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("Perigo Potencial", SeveridadeAviso.PERIGO_POTENCIAL),
            ("Perigo", SeveridadeAviso.PERIGO),
            ("Grande Perigo", SeveridadeAviso.GRANDE_PERIGO),
            (" grande perigo ", SeveridadeAviso.GRANDE_PERIGO),
        ],
    )
    def test_escala_do_inmet(self, texto, esperado):
        assert SeveridadeAviso.from_inmet(texto) is esperado


class TestAvisoMeteorologico:
    def _base(self, **mudancas):
        campos = dict(
            codigo_cap="urn:x", id_aviso=1, id_sequencia=1, evento="Tempestade",
            severidade=SeveridadeAviso.PERIGO, codigos_ibge=frozenset({3550308}),
            inicio=datetime(2026, 11, 23, 3, tzinfo=timezone.utc),
            fim=datetime(2026, 11, 24, 2, 59, tzinfo=timezone.utc),
        )
        campos.update(mudancas)
        return AvisoMeteorologico(**campos)

    def test_instante_sem_fuso_e_recusado(self):
        with pytest.raises(ValueError, match="fuso"):
            self._base(inicio=datetime(2026, 11, 23, 3))

    def test_fim_antes_do_inicio_e_recusado(self):
        with pytest.raises(ValueError, match="termina antes"):
            self._base(fim=datetime(2026, 11, 22, tzinfo=timezone.utc))

    def test_codigo_ibge_fora_do_formato_e_recusado(self):
        with pytest.raises(ValueError, match="7 dígitos"):
            self._base(codigos_ibge=frozenset({123}))


class TestColetar:
    def test_coleta_hoje_e_futuro(self):
        avisos, descartados = InmetSource(opener=_opener(PAYLOAD)).coletar()
        assert sorted(a.id_aviso for a in avisos) == [28743, 28746, 28747]
        assert descartados == 0

    def test_mesmo_aviso_em_hoje_e_futuro_conta_uma_vez(self):
        payload = copy.deepcopy(PAYLOAD)
        payload["futuro"].append(copy.deepcopy(payload["hoje"][0]))
        avisos, _ = InmetSource(opener=_opener(payload)).coletar()
        assert len(avisos) == 3

    def test_item_malformado_e_descartado_e_os_outros_seguem(self):
        payload = copy.deepcopy(PAYLOAD)
        payload["hoje"].append({"codigo": "x"})
        avisos, descartados = InmetSource(opener=_opener(payload)).coletar()
        assert (len(avisos), descartados) == (3, 1)

    @pytest.mark.parametrize("payload", [[], {"hoje": []}, {"hoje": [], "futuro": "x"}])
    def test_envelope_desconhecido_vira_falha_de_coleta(self, payload):
        with pytest.raises(FalhaDeColeta, match="formato de payload"):
            InmetSource(opener=_opener(payload)).coletar()
