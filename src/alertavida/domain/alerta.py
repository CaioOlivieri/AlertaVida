"""Modelo de domínio do Alerta — Camada 2 + refator Camada 4 Parte A.1.2.

Invariantes do `Alerta`:
- `cod_alerta` é string não-vazia. Suporta CEMADEN ("1854") e EONET ("EONET_5421").
- `coordenadas` é OBRIGATÓRIO. Alerta sem localização geográfica não entra no
  sistema (princípio de honestidade dos dados — ver wiki/patterns/code-conventions.md).
- `municipio` é opcional e descritivo. Pode ser None quando a fonte não fornece.
- `escopo_geografico` é atributo do domínio mas calculado externamente em
  `monitor.py` via `geographic.classificar_escopo()` (Camada 4 Parte A.1.4).
  Default `INDETERMINADO` é o valor seguro até a classificação acontecer.
- `descricao` é opcional. Atualmente write-only — `NasaEonetSource` já o
  popula com o título do evento, mas a persistência (`database.py`) e o
  payload de eventos (`detector._payload_de`) ainda não o incluem, então o
  dado é descartado ao final da ingestão. Decisão de persistir ou não
  pendente (issue #11 D4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    ValidationError,
    field_validator,
    model_validator,
)

from alertavida.domain.cobrade import validar_formato as _validar_formato_cobrade
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import (
    EscopoGeografico,
    FonteClassificacao,
    FonteDado,
    NivelRisco,
    TipoEvento,
)
from alertavida.domain.municipio import Municipio


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return val
    return None


class Alerta(BaseModel):
    cod_alerta: str = Field(min_length=1)
    fonte: Annotated[FonteDado, Strict()]
    tipo_evento: TipoEvento
    nivel_risco: NivelRisco
    coordenadas: Coordenadas
    municipio: Municipio | None = None
    escopo_geografico: EscopoGeografico = EscopoGeografico.INDETERMINADO
    data_criacao: datetime
    ult_atualizacao: datetime | None = None
    descricao: str | None = None
    cobrade_codigo: str | None = None
    fonte_classificacao: FonteClassificacao = FonteClassificacao.INDETERMINADA

    model_config = ConfigDict(frozen=True)

    @field_validator("cobrade_codigo")
    @classmethod
    def _validar_formato(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _validar_formato_cobrade(v):
            raise ValueError(
                f"cobrade_codigo inválido: {v!r}. Formato esperado: N.N.N.N.N"
            )
        return v

    @model_validator(mode="after")
    def _validar_invariante_classificacao(self) -> "Alerta":
        """
        Invariante: cobrade_codigo e fonte_classificacao mudam atomicamente.

        - cobrade_codigo IS NULL    ⇔ fonte_classificacao == INDETERMINADA
        - cobrade_codigo IS NOT NULL ⇔ fonte_classificacao != INDETERMINADA

        Ver wiki/patterns/resilience-invariants.md e
        wiki/projects/layer-4-multi-source-ingestion.md.
        """
        tem_codigo = self.cobrade_codigo is not None
        eh_indeterminada = self.fonte_classificacao == FonteClassificacao.INDETERMINADA
        if tem_codigo == eh_indeterminada:
            raise ValueError(
                "Invariante violada: cobrade_codigo e fonte_classificacao "
                "devem mudar juntos. "
                f"cobrade_codigo={self.cobrade_codigo!r}, "
                f"fonte_classificacao={self.fonte_classificacao.value}"
            )
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, fonte: FonteDado) -> "Alerta":
        cod_raw = _pick(data, "codigoalerta", "cod_alerta", "id", "codigo")
        if cod_raw is None:
            raise ValueError("Alerta sem cod_alerta válido")
        cod_alerta = str(cod_raw).strip()
        if not cod_alerta:
            raise ValueError("Alerta sem cod_alerta válido")

        tipo_raw = _pick(data, "tipo_evento", "evento", "tipo", "desastre", "tipoevento")
        if tipo_raw is None or not str(tipo_raw).strip():
            raise ValueError("Alerta sem tipo_evento")
        tipo_evento = TipoEvento.from_string(str(tipo_raw))

        nivel_raw = _pick(data, "nivel", "nivel_alerta", "severity", "grau")
        try:
            nivel_risco = NivelRisco.from_string(None if nivel_raw is None else str(nivel_raw))
        except ValueError:
            if nivel_raw is None or not str(nivel_raw).strip():
                raise ValueError("Alerta sem nivel_risco") from None
            raise

        latitude = _pick(data, "latitude", "lat")
        longitude = _pick(data, "longitude", "lon", "lng")
        if latitude is None or longitude is None:
            raise ValueError("Alerta sem coordenadas válidas")
        try:
            coordenadas = Coordenadas(latitude=float(latitude), longitude=float(longitude))
        except (TypeError, ValueError, ValidationError):
            raise ValueError("Alerta sem coordenadas válidas") from None

        dt_raw = _pick(data, "datahoracriacao", "data_criacao", "dataCriacao", "dt_criacao")
        if dt_raw is None or not str(dt_raw).strip():
            raise ValueError("Alerta sem data_criacao")
        try:
            data_criacao = datetime.fromisoformat(str(dt_raw))
        except ValueError:
            raise ValueError("Alerta sem data_criacao válido") from None
        if data_criacao.tzinfo is None:
            data_criacao = data_criacao.replace(tzinfo=timezone.utc)

        ult_raw = _pick(data, "ult_atualizacao", "ultima_atualizacao", "dataAtualizacao")
        ult_atualizacao = None
        if ult_raw is not None and str(ult_raw).strip():
            try:
                ult_atualizacao = datetime.fromisoformat(str(ult_raw))
                if ult_atualizacao.tzinfo is None:
                    ult_atualizacao = ult_atualizacao.replace(tzinfo=timezone.utc)
            except ValueError:
                ult_atualizacao = None

        nome = _pick(data, "municipio", "nome_municipio", "cidade")
        uf = _pick(data, "uf", "estado", "state")
        municipio = None
        if nome is not None and str(nome).strip() and uf is not None and str(uf).strip():
            ibge_raw = _pick(data, "codibge", "codigo_ibge", "ibge", "codigoIbge")
            codigo_ibge = None
            if ibge_raw is not None:
                try:
                    codigo_ibge = int(ibge_raw)
                except (TypeError, ValueError):
                    codigo_ibge = None
            try:
                municipio = Municipio(
                    nome=str(nome).strip(),
                    uf=str(uf).strip(),
                    codigo_ibge=codigo_ibge,
                )
            except ValidationError:
                municipio = None

        descricao = _pick(data, "descricao", "desc", "mensagem")

        return cls(
            cod_alerta=cod_alerta,
            fonte=fonte,
            tipo_evento=tipo_evento,
            nivel_risco=nivel_risco,
            coordenadas=coordenadas,
            municipio=municipio,
            data_criacao=data_criacao,
            ult_atualizacao=ult_atualizacao,
            descricao=None if descricao is None else str(descricao),
        )
