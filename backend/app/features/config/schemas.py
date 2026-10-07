from typing import Literal
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

IconName = Literal["calendar", "clipboard", "stethoscope", "pin", "book", "search"]


class CamelModel(BaseModel):
    # 프론트 TS 타입(camelCase)과 맞추기 위해 alias 사용
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MenuItem(CamelModel):
    id: str
    label: str
    description: str | None = None
    icon: IconName
    intent: str
    requires_auth: bool = False
    order: int
    visible: bool = True


class HeroConfig(CamelModel):
    eyebrow: str
    title: str
    description: str
    cta_label: str
    intent: str


class ChatConfig(CamelModel):
    hospital_name: str
    is_operating_hours: bool
    operating_hours_text: str
    hero: HeroConfig
    tiles: list[MenuItem]
    faqs: list[MenuItem]
    disclaimer: str
