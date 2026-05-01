from pydantic import BaseModel, ConfigDict, Field, field_validator

from alertavida.domain.coordenadas import Coordenadas


class Municipio(BaseModel):
    nome: str = Field(min_length=1)
    uf: str = Field(min_length=2, max_length=2)
    codigo_ibge: int | None = None
    coordenadas: Coordenadas | None = None

    model_config = ConfigDict(frozen=True)

    @field_validator("uf", mode="before")
    @classmethod
    def normalize_uf(cls, value):
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("nome", mode="before")
    @classmethod
    def normalize_nome(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value
