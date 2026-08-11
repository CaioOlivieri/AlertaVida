"""`Incidente` — agregado de N `Alerta`s referindo-se ao mesmo evento físico
observado por fontes diferentes (Camada 5, issue #58).

Núcleo 100% puro: nenhum I/O, nenhuma consulta a banco. Decidir QUAIS
alertas formam um `Incidente` é responsabilidade de `domain/correlacao.py`;
este módulo só modela o agregado resultante e a agregação de severidade
(Round 1, Q3 — ver wiki/projects/layer-5-correlation.md).

Fusão de incidentes (`fundido_em`) e a regra de "quando resolver" dependem de
estado persistido (id, membros reais em banco) e ficam para #59/#61 — este
módulo modela a forma do agregado, não as transições de ciclo de vida.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alertavida.domain.enums import FonteDado, NivelRisco

# Ordem de severidade para a agregação por MÁXIMO (Round 1, Q3). INDETERMINADO
# fica de fora deste mapa de propósito: é excluído do máximo, nunca tratado
# como "mais baixo que BAIXO" — isso transformaria ausência de informação em
# informação, exatamente o erro que a decisão evita.
_ORDEM_SEVERIDADE: Final[dict[NivelRisco, int]] = {
    NivelRisco.BAIXO: 0,
    NivelRisco.MODERADO: 1,
    NivelRisco.ALTO: 2,
    NivelRisco.MUITO_ALTO: 3,
}


class StatusIncidente(StrEnum):
    """Espelha `alertas.status_interno` (Round 1, Q5)."""

    ATIVO = "ATIVO"
    RESOLVIDO = "RESOLVIDO"


class MembroIncidente(BaseModel):
    """Referência a um `Alerta` membro, pela chave natural (fonte, cod_alerta)
    — a mesma que `UNIQUE (fonte, cod_alerta)` garante em `alertas`
    (ver [[components/domain-models]]).

    Carrega `nivel_risco` além da chave porque a agregação de severidade do
    `Incidente` precisa dele e este módulo não faz I/O para buscá-lo — quem
    monta o `Incidente` (infra, #59/#61) já tem o `Alerta` em mãos.
    """

    fonte: FonteDado
    cod_alerta: str = Field(min_length=1)
    nivel_risco: NivelRisco

    model_config = ConfigDict(frozen=True)


class Incidente(BaseModel):
    """Agregado de `Alerta`s que descrevem o mesmo evento físico.

    Espelha o ciclo de vida já existente em `alertas.status_interno`
    (Round 1, Q5): ATIVO/RESOLVIDO, deve poder reativar. Resolve só quando
    TODOS os membros resolvem — mas essa transição depende do estado real dos
    Alertas em banco, então a regra em si vive na integração (#61); aqui só a
    forma (`status`/`resolvido_em`) é modelada.
    """

    membros: tuple[MembroIncidente, ...] = Field(min_length=1)
    status: StatusIncidente = StatusIncidente.ATIVO
    criado_em: datetime
    atualizado_em: datetime
    resolvido_em: datetime | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validar_membros_unicos(self) -> "Incidente":
        chaves = [(m.fonte, m.cod_alerta) for m in self.membros]
        if len(chaves) != len(set(chaves)):
            raise ValueError("Incidente com membros duplicados (mesma fonte + cod_alerta)")
        return self

    @model_validator(mode="after")
    def _validar_invariante_resolucao(self) -> "Incidente":
        """Invariante atômica, mesmo estilo de
        `Alerta._validar_invariante_classificacao`:
        resolvido_em IS NOT NULL ⇔ status == RESOLVIDO.
        """
        tem_resolvido_em = self.resolvido_em is not None
        esta_resolvido = self.status == StatusIncidente.RESOLVIDO
        if tem_resolvido_em != esta_resolvido:
            raise ValueError(
                "Invariante violada: resolvido_em e status devem mudar juntos. "
                f"resolvido_em={self.resolvido_em!r}, status={self.status.value}"
            )
        return self

    @property
    def severidade(self) -> NivelRisco | None:
        """Severidade agregada = MÁXIMO entre membros com nível conhecido.

        Nunca a média — um `INDETERMINADO` não pode diluir um `MUITO_ALTO`
        (Round 1, Q3). Retorna `None` quando todos os membros são
        `INDETERMINADO` (severidade desconhecida, não "baixa").
        """
        conhecidos = [m.nivel_risco for m in self.membros if m.nivel_risco in _ORDEM_SEVERIDADE]
        if not conhecidos:
            return None
        return max(conhecidos, key=lambda nivel: _ORDEM_SEVERIDADE[nivel])

    @property
    def membros_sem_severidade(self) -> int:
        """Quantos membros publicam `NivelRisco.INDETERMINADO`.

        Contados, mas excluídos de `severidade` — ausência de severidade é
        registrada, nunca tratada como evidência de baixa severidade.
        """
        return sum(1 for m in self.membros if m.nivel_risco == NivelRisco.INDETERMINADO)
