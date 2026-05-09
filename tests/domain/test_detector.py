"""Testes do ChangeDetector (detecção pura de mudanças).

Atualizado em A.1.4: cod_alerta como string, payload com fonte/coordenadas/escopo.
"""

from alertavida.domain.alerta import Alerta
from alertavida.domain.detector import (
    AlertaSnapshot,
    RODADAS_PARA_RESOLVER,
    detectar_mudancas,
)


FONTE_TESTE = "CEMADEN"


def _payload_base_cemaden(cod: int | str) -> dict:
    return {
        "codigoalerta": cod,
        "municipio": "Recife",
        "estado": "PE",
        "tipoevento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }


def test_alerta_novo_gera_evento_criado() -> None:
    payload = {
        **_payload_base_cemaden(9001),
        "ult_atualizacao": "2026-04-29T11:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload)
    res = detectar_mudancas([alerta], [], FONTE_TESTE)
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo == "AlertaCriado"
    assert res.eventos[0].cod_alerta == "9001"
    assert res.eventos[0].payload["fonte"] == "CEMADEN"
    assert res.eventos[0].payload["coordenadas"]["latitude"] == -8.05


def test_alerta_inalterado_nao_gera_evento() -> None:
    ult = "2026-04-29T11:00:00+00:00"
    payload = {**_payload_base_cemaden(9002), "ult_atualizacao": ult}
    alerta = Alerta.from_dict(payload)
    snap = AlertaSnapshot(
        cod_alerta="9002",
        nivel_risco=alerta.nivel_risco.value,
        tipo_evento=alerta.tipo_evento.value,
        ult_atualizacao=ult,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([alerta], [snap], FONTE_TESTE)
    assert res.eventos == []


def test_alerta_atualizado_gera_evento_atualizado() -> None:
    payload = {
        **_payload_base_cemaden(9003),
        "ult_atualizacao": "2026-05-01T14:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload)
    snap = AlertaSnapshot(
        cod_alerta="9003",
        nivel_risco=alerta.nivel_risco.value,
        tipo_evento=alerta.tipo_evento.value,
        ult_atualizacao="2026-04-29T09:00:00+00:00",
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([alerta], [snap], FONTE_TESTE)
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo == "AlertaAtualizado"
    assert res.eventos[0].cod_alerta == "9003"


def test_alerta_ausente_incrementa_ausente() -> None:
    cod = "9004"
    snap = AlertaSnapshot(
        cod_alerta=cod,
        nivel_risco="MODERADO",
        tipo_evento="HIDROLOGICO",
        ult_atualizacao="2026-04-29T09:00:00+00:00",
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([], [snap], FONTE_TESTE)
    assert res.codigos_ausentes == {cod}
    assert res.codigos_resolvidos == set()


def test_alerta_ausente_resolve_apos_limite() -> None:
    cod = "9005"
    snap = AlertaSnapshot(
        cod_alerta=cod,
        nivel_risco="ALTO",
        tipo_evento="HIDROLOGICO",
        ult_atualizacao=None,
        rodadas_ausente=2,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([], [snap], FONTE_TESTE, rodadas_para_resolver=3)
    assert res.codigos_resolvidos == {cod}
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo == "AlertaResolvido"
    assert res.eventos[0].payload["fonte"] == "CEMADEN"
    assert res.codigos_ausentes == set()


def test_alerta_resolvido_no_banco_nao_reativa() -> None:
    payload = {
        **_payload_base_cemaden(9006),
        "ult_atualizacao": "2026-05-02T08:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload)
    snap = AlertaSnapshot(
        cod_alerta="9006",
        nivel_risco="BAIXO",
        tipo_evento="INDETERMINADO",
        ult_atualizacao=None,
        rodadas_ausente=0,
        status_interno="RESOLVIDO",
    )
    res = detectar_mudancas([alerta], [snap], FONTE_TESTE)
    assert res.eventos == []


def test_multiplos_alertas_mix() -> None:
    ult_existente = "2026-04-29T12:00:00+00:00"
    novo_payload = {
        **_payload_base_cemaden(9100),
        "ult_atualizacao": "2026-05-03T09:00:00+00:00",
    }
    existe_payload = {
        **_payload_base_cemaden(9200),
        "ult_atualizacao": ult_existente,
    }
    alerta_novo = Alerta.from_dict(novo_payload)
    alerta_igual = Alerta.from_dict(existe_payload)

    snap_igual = AlertaSnapshot(
        cod_alerta="9200",
        nivel_risco=alerta_igual.nivel_risco.value,
        tipo_evento=alerta_igual.tipo_evento.value,
        ult_atualizacao=ult_existente,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    snap_ausente = AlertaSnapshot(
        cod_alerta="9300",
        nivel_risco="MODERADO",
        tipo_evento="GEOLOGICO",
        ult_atualizacao=None,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )

    res = detectar_mudancas(
        [alerta_novo, alerta_igual],
        [snap_igual, snap_ausente],
        FONTE_TESTE,
        rodadas_para_resolver=RODADAS_PARA_RESOLVER,
    )

    tipos = [e.tipo for e in res.eventos]
    assert tipos.count("AlertaCriado") == 1
    assert tipos.count("AlertaAtualizado") == 0
    assert res.codigos_ausentes == {"9300"}
    assert res.codigos_resolvidos == set()
