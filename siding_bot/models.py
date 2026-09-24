from typing import Literal

from pydantic import BaseModel, Field

RoofType = Literal["gable", "hip", "shed", "flat"]

ROOF_NAMES: dict[str, str] = {
    "gable": "двускатная (2 фронтона)",
    "hip": "вальмовая (без фронтонов)",
    "shed": "односкатная",
    "flat": "плоская",
}


class Opening(BaseModel):
    width_m: float = Field(description="Ширина проёма, м")
    height_m: float = Field(description="Высота проёма, м")
    count: int = Field(description="Сколько таких проёмов на всём доме")


class House(BaseModel):
    """Геометрия дома для расчёта. Дом считается прямоугольным в плане."""

    length_m: float = Field(description="Длина дома по стене под свесом кровли (карнизная сторона), м")
    width_m: float = Field(description="Ширина дома по торцу (сторона с фронтоном), м")
    wall_height_m: float = Field(description="Высота стен от цоколя до карниза, м")
    roof_type: RoofType = Field(description="Тип кровли")
    gable_height_m: float = Field(
        description="Высота фронтона от карниза до конька, м (для односкатной — перепад высот; 0 для вальмовой и плоской)"
    )
    outside_corners: int = Field(description="Количество наружных углов дома (у прямоугольного — 4)")
    inside_corners: int = Field(description="Количество внутренних углов (0, если их нет)")
    windows: list[Opening] = Field(description="Окна, сгруппированные по одинаковым размерам")
    doors: list[Opening] = Field(description="Двери, сгруппированные по одинаковым размерам")


class FacadeAnalysis(House):
    """Ответ модели по фотографиям: геометрия плюс пояснения."""

    comment: str = Field(
        description="Кратко на русском: что видно на фото, что пришлось додумать (например, скрытые стороны)"
    )
