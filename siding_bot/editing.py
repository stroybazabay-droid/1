"""Разбор ввода пользователя и правка параметров дома."""

import re

from .models import House, Opening

DIMENSIONS = ("length_m", "width_m", "wall_height_m")


class InputError(ValueError):
    pass


def parse_number(text: str, low: float = 0.1, high: float = 100) -> float:
    try:
        value = float(text.strip().replace(",", ".").rstrip("мm ").strip())
    except ValueError:
        raise InputError("Нужно число, например 8,5") from None
    if not low <= value <= high:
        raise InputError(f"Значение должно быть от {low:g} до {high:g}")
    return value


def parse_openings(text: str) -> list[Opening]:
    """«1,2х1,4х6; 0,9х2,1х1» → список проёмов (ширина × высота × количество)."""
    text = text.strip()
    if text in ("0", "-", "нет"):
        return []
    result = []
    for part in re.split(r"[;\n]+", text):
        part = part.strip()
        if not part:
            continue
        nums = re.split(r"\s*[xх×*]\s*", part.replace(",", "."), flags=re.IGNORECASE)
        if len(nums) != 3:
            raise InputError(f"Не понял «{part}». Формат: ширина×высота×количество, например 1,2х1,4х6")
        try:
            width, height, count = float(nums[0]), float(nums[1]), int(float(nums[2]))
        except ValueError:
            raise InputError(f"Не понял «{part}». Формат: ширина×высота×количество") from None
        if not (0.1 <= width <= 10 and 0.1 <= height <= 10 and 1 <= count <= 200):
            raise InputError(f"Странные размеры в «{part}»")
        result.append(Opening(width_m=width, height_m=height, count=count))
    return result


def parse_corners(text: str) -> tuple[int, int]:
    """«4» или «6 2» → (наружные, внутренние)."""
    nums = re.findall(r"\d+", text)
    if not 1 <= len(nums) <= 2:
        raise InputError("Введите количество наружных углов и, через пробел, внутренних: например 6 2")
    outside = int(nums[0])
    inside = int(nums[1]) if len(nums) == 2 else 0
    if outside > 50 or inside > 50:
        raise InputError("Слишком много углов")
    return outside, inside


def set_dimension(house: House, field: str, value: float, confirmed: set[str]) -> House:
    """Меняет длину/ширину/высоту.

    Первый уточнённый размер задаёт масштаб фото: остальные неподтверждённые
    размеры и фронтон пересчитываются пропорционально. Потом каждый размер
    правится отдельно, а фронтон следует за шириной, сохраняя уклон кровли.
    """
    old = getattr(house, field)
    data = house.model_dump()
    data[field] = value
    confirmed.add(field)

    if old > 0:
        ratio = value / old
        if len(confirmed & set(DIMENSIONS)) == 1:
            for other in DIMENSIONS:
                if other not in confirmed:
                    data[other] = round(data[other] * ratio, 2)
            if "gable_height_m" not in confirmed:
                data["gable_height_m"] = round(data["gable_height_m"] * ratio, 2)
        elif field == "width_m" and "gable_height_m" not in confirmed:
            data["gable_height_m"] = round(data["gable_height_m"] * ratio, 2)
    return House.model_validate(data)
