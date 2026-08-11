"""Testes do modelo Incidente e da agregação de severidade (Round 1, Q3)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from alertavida.domain.enums import FonteDado, NivelRisco
from alertavida.domain.incidente import Incidente, MembroIncidente, StatusIncidente

_AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _membro(
    cod: str, nivel: NivelRisco, fonte: FonteDado = FonteDado.CEMADEN
) -> MembroIncidente:
    return MembroIncidente(fonte=fonte, cod_alerta=cod, nivel_risco=nivel)


def _incidente(
    membros: list[MembroIncidente],
    status: StatusIncidente = StatusIncidente.ATIVO,
    resolvido_em: datetime | None = None,
) -> Incidente:
    return Incidente(
        membros=tuple(membros),
        status=status,
        criado_em=_AGORA,
        atualizado_em=_AGORA,
        resolvido_em=resolvido_em,
    )


def test_severidade_e_o_maximo_entre_membros_conhecidos() -> None:
    incidente = _incidente(
        [
            _membro("A1", NivelRisco.MODERADO),
            _membro("A2", NivelRisco.MUITO_ALTO, fonte=FonteDado.EONET),
        ]
    )
    assert incidente.severidade == NivelRisco.MUITO_ALTO


def test_membro_indeterminado_nao_dilui_severidade_maxima() -> None:
    """Round 1 Q3: a média é proibida — um INDETERMINADO não pode 'puxar
    para baixo' um MUITO_ALTO."""
    incidente = _incidente(
        [
            _membro("A1", NivelRisco.MUITO_ALTO),
            _membro("A2", NivelRisco.INDETERMINADO, fonte=FonteDado.EONET),
        ]
    )
    assert incidente.severidade == NivelRisco.MUITO_ALTO
    assert incidente.membros_sem_severidade == 1


def test_severidade_none_quando_todos_membros_sao_indeterminados() -> None:
    incidente = _incidente(
        [
            _membro("A1", NivelRisco.INDETERMINADO),
            _membro("A2", NivelRisco.INDETERMINADO, fonte=FonteDado.EONET),
        ]
    )
    assert incidente.severidade is None
    assert incidente.membros_sem_severidade == 2


def test_membros_sem_severidade_conta_mas_nao_participa_do_maximo() -> None:
    incidente = _incidente(
        [
            _membro("A1", NivelRisco.BAIXO),
            _membro("A2", NivelRisco.INDETERMINADO, fonte=FonteDado.EONET),
            _membro("A3", NivelRisco.INDETERMINADO, fonte=FonteDado.INMET),
        ]
    )
    assert incidente.severidade == NivelRisco.BAIXO
    assert incidente.membros_sem_severidade == 2


def test_membros_duplicados_rejeitado() -> None:
    with pytest.raises(ValidationError):
        _incidente(
            [
                _membro("A1", NivelRisco.ALTO),
                _membro("A1", NivelRisco.BAIXO),
            ]
        )


def test_incidente_sem_membros_rejeitado() -> None:
    with pytest.raises(ValidationError):
        _incidente([])


def test_status_resolvido_exige_resolvido_em() -> None:
    with pytest.raises(ValidationError):
        _incidente([_membro("A1", NivelRisco.ALTO)], status=StatusIncidente.RESOLVIDO)


def test_resolvido_em_exige_status_resolvido() -> None:
    with pytest.raises(ValidationError):
        _incidente([_membro("A1", NivelRisco.ALTO)], resolvido_em=_AGORA)


def test_incidente_resolvido_com_resolvido_em_valido() -> None:
    incidente = _incidente(
        [_membro("A1", NivelRisco.ALTO)],
        status=StatusIncidente.RESOLVIDO,
        resolvido_em=_AGORA,
    )
    assert incidente.status == StatusIncidente.RESOLVIDO
    assert incidente.resolvido_em == _AGORA
