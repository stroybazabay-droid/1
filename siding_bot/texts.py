from html import escape

from .calculator import Estimate
from .models import ROOF_NAMES, House, Opening

START = (
    "Привет! Я считаю виниловый сайдинг U-Plast и комплектующие.\n\n"
    "1. Пришлите 1–5 фото дома (лучше с разных сторон, целиком в кадре).\n"
    "2. Нажмите «Анализировать» — я оценю размеры, окна и двери.\n"
    "3. Уточните хотя бы один размер (например, длину дома) — остальные я пересчитаю пропорционально.\n"
    "4. Нажмите «Рассчитать» и получите смету.\n\n"
    "Можно и без фото: /manual — ввести размеры вручную.\n"
    "Начать заново: /new"
)


def _num(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def openings_text(openings: list[Opening]) -> str:
    if not openings:
        return "нет"
    return "; ".join(f"{_num(o.width_m)}×{_num(o.height_m)} м — {o.count} шт" for o in openings)


def house_card(house: House, confirmed: set[str], comment: str | None = None) -> str:
    def mark(field: str) -> str:
        return "" if field in confirmed else "≈"

    lines = ["<b>Параметры дома</b>"]
    if comment:
        lines.append(f"<i>{escape(comment)}</i>\n")
    lines += [
        f"Длина (карнизная сторона): {mark('length_m')}{_num(house.length_m)} м",
        f"Ширина (торец): {mark('width_m')}{_num(house.width_m)} м",
        f"Высота стен до карниза: {mark('wall_height_m')}{_num(house.wall_height_m)} м",
        f"Кровля: {ROOF_NAMES[house.roof_type]}",
    ]
    if house.roof_type in ("gable", "shed"):
        lines.append(f"Высота фронтона: {mark('gable_height_m')}{_num(house.gable_height_m)} м")
    lines += [
        f"Углы: наружных {house.outside_corners}, внутренних {house.inside_corners}",
        f"Окна: {openings_text(house.windows)}",
        f"Двери: {openings_text(house.doors)}",
    ]
    if len(confirmed) < 3:
        lines.append("\n≈ — оценка по фото. Уточните размеры кнопками ниже, это сильно влияет на точность.")
    return "\n".join(lines)


def estimate_text(est: Estimate) -> str:
    cur = est.currency
    lines = [
        "<b>Расчёт сайдинга</b>",
        f"Стены: {_num(est.wall_area)} м²",
    ]
    if est.gable_area:
        lines.append(f"Фронтоны: {_num(est.gable_area)} м²")
    lines += [
        f"Минус проёмы: {_num(est.openings_area)} м²",
        f"<b>Площадь обшивки: {_num(est.net_area)} м²</b>\n",
    ]
    for line in est.lines:
        lines.append(
            f"• {escape(line.name)}: <b>{line.qty} {line.unit}</b>"
            f" × {_money(line.price)} = {_money(line.total)} {cur}"
        )
    lines.append(f"\n<b>Итого: {_money(est.total)} {cur}</b>")
    lines.append("\nРасчёт ориентировочный: перед заказом сверьте размеры на объекте.")
    return "\n".join(lines)
