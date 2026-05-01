from pydantic import BaseModel, ConfigDict, Field


class Coordenadas(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    model_config = ConfigDict(frozen=True)
