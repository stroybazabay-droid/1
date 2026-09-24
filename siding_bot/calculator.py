import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .models import House

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "catalog.json"


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Line:
    name: str
    qty: int
    unit: str
    price: float

    @property
    def total(self) -> float:
        return self.qty * self.price


@dataclass
class Estimate:
    wall_area: float
    gable_area: float
    openings_area: float
    net_area: float
    lines: list[Line] = field(default_factory=list)
    currency: str = "₽"

    @property
    def total(self) -> float:
        return sum(line.total for line in self.lines)


def _pieces(length_m: float, piece_len: float, reserve: float) -> int:
    if length_m <= 0:
        return 0
    return math.ceil(length_m * (1 + reserve) / piece_len)


def calculate(house: House, catalog: dict) -> Estimate:
    items = catalog["items"]
    waste = catalog["waste_percent"] / 100
    reserve = catalog["profile_reserve_percent"] / 100

    L, W, H = house.length_m, house.width_m, house.wall_height_m
    gh = house.gable_height_m if house.roof_type in ("gable", "shed") else 0.0

    wall_area = 2 * (L + W) * H

    # Фронтоны, кровельные скаты (J-профиль) и карнизы (финишная планка).
    if house.roof_type == "gable":
        gable_area = 2 * 0.5 * W * gh
        rake_len = 2 * 2 * math.hypot(W / 2, gh)
        eaves_len = 2 * L
    elif house.roof_type == "shed":
        # Два треугольника на торцах плюс надстройка высокой стены.
        gable_area = 2 * 0.5 * W * gh + L * gh
        rake_len = 2 * math.hypot(W, gh)
        eaves_len = 2 * L
    else:
        gable_area = 0.0
        rake_len = 0.0
        eaves_len = 2 * (L + W)

    windows_area = sum(o.width_m * o.height_m * o.count for o in house.windows)
    doors_area = sum(o.width_m * o.height_m * o.count for o in house.doors)
    openings_area = windows_area + doors_area
    net_area = max(wall_area + gable_area - openings_area, 0.0)

    panel = items["panel"]
    panel_area = panel["length_m"] * panel["working_width_m"]
    panels = math.ceil(net_area * (1 + waste) / panel_area) if net_area else 0

    doors_width = sum(o.width_m * o.count for o in house.doors)
    starter_len = max(2 * (L + W) - doors_width, 0.0)

    corner_len = items["outside_corner"]["length_m"]
    outside = house.outside_corners * math.ceil(H / corner_len)
    inside = house.inside_corners * math.ceil(H / items["inside_corner"]["length_m"])

    trim_len = sum(2 * (o.width_m + o.height_m) * o.count for o in house.windows)
    trim_len += sum((o.width_m + 2 * o.height_m) * o.count for o in house.doors)

    sills_len = sum(o.width_m * o.count for o in house.windows)
    finish_len = eaves_len + sills_len

    profiles = {
        "starter": _pieces(starter_len, items["starter"]["length_m"], reserve),
        "outside_corner": outside,
        "inside_corner": inside,
        "window_trim": _pieces(trim_len, items["window_trim"]["length_m"], reserve),
        "finish": _pieces(finish_len, items["finish"]["length_m"], reserve),
        "j_channel": _pieces(rake_len, items["j_channel"]["length_m"], reserve),
    }

    # Панели учтены в норме на м², доборные элементы — поштучно.
    fastener_count = net_area * catalog["fasteners_per_m2"] + sum(profiles.values()) * catalog["fasteners_per_profile"]
    fastener_packs = math.ceil(fastener_count / items["fasteners"]["pack_size"])

    quantities = {"panel": panels, **profiles, "fasteners": fastener_packs}
    lines = [
        Line(items[key]["name"], qty, items[key]["unit"], items[key]["price"])
        for key, qty in quantities.items()
        if qty > 0
    ]

    return Estimate(
        wall_area=wall_area,
        gable_area=gable_area,
        openings_area=openings_area,
        net_area=net_area,
        lines=lines,
        currency=catalog.get("currency", "₽"),
    )
