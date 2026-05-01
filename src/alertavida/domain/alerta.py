from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import NivelRisco, TipoEvento
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
    cod_alerta: int = Field(gt=0)
    tipo_evento: TipoEvento
    nivel_risco: NivelRisco
    municipio: Municipio
    coordenadas: Coordenadas | None = None
    data_criacao: datetime
    descricao: str | None = None

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Alerta":
        cod_raw = _pick(data, "codigoalerta", "cod_alerta", "id", "codigo")
        try:
            cod_alerta = int(cod_raw)
            if cod_alerta <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Alerta sem cod_alerta válido") from None

        nome = _pick(data, "municipio", "nome_municipio", "cidade")
        if nome is None or not str(nome).strip():
            raise ValueError("Alerta sem municipio.nome")

        uf = _pick(data, "uf", "estado", "state")
        if uf is None or not str(uf).strip():
            raise ValueError("Alerta sem municipio.uf")

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

        dt_raw = _pick(data, "datahoracriacao", "data_criacao", "dataCriacao", "dt_criacao")
        if dt_raw is None or not str(dt_raw).strip():
            raise ValueError("Alerta sem data_criacao")
        try:
            data_criacao = datetime.fromisoformat(str(dt_raw))
        except ValueError:
            raise ValueError("Alerta sem data_criacao válido") from None
        if data_criacao.tzinfo is None:
            data_criacao = data_criacao.replace(tzinfo=timezone.utc)

        latitude = _pick(data, "latitude", "lat")
        longitude = _pick(data, "longitude", "lon", "lng")
        coordenadas = None
        if latitude is not None and longitude is not None:
            try:
                coordenadas = Coordenadas(latitude=float(latitude), longitude=float(longitude))
            except (TypeError, ValueError, ValidationError):
                coordenadas = None

        descricao = _pick(data, "descricao", "desc", "mensagem")
        municipio = Municipio(nome=str(nome).strip(), uf=str(uf).strip())

        return cls(
            cod_alerta=cod_alerta,
            tipo_evento=tipo_evento,
            nivel_risco=nivel_risco,
            municipio=municipio,
            coordenadas=coordenadas,
            data_criacao=data_criacao,
            descricao=None if descricao is None else str(descricao),
        )
