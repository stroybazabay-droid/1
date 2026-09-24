import math

import pytest

from siding_bot.calculator import calculate, load_catalog
from siding_bot.editing import InputError, parse_corners, parse_openings, set_dimension
from siding_bot.models import House, Opening


def make_house(**kw) -> House:
    data = dict(
        length_m=10,
        width_m=8,
        wall_height_m=3,
        roof_type="gable",
        gable_height_m=2,
        outside_corners=4,
        inside_corners=0,
        windows=[Opening(width_m=1.2, height_m=1.4, count=6)],
        doors=[Opening(width_m=0.9, height_m=2.1, count=1)],
    )
    data.update(kw)
    return House(**data)


@pytest.fixture
def catalog():
    return load_catalog()


def qty(est, name_part):
    return next(line.qty for line in est.lines if name_part in line.name)


def test_areas_gable(catalog):
    est = calculate(make_house(), catalog)
    assert est.wall_area == pytest.approx(108)
    assert est.gable_area == pytest.approx(16)  # 2 треугольника 8×2/2
    assert est.openings_area == pytest.approx(6 * 1.68 + 1.89)
    assert est.net_area == pytest.approx(108 + 16 - 11.97)


def test_panels_include_waste(catalog):
    est = calculate(make_house(), catalog)
    panel_area = 3.66 * 0.23
    assert qty(est, "Панель") == math.ceil(est.net_area * 1.1 / panel_area)


def test_profiles(catalog):
    est = calculate(make_house(), catalog)
    assert qty(est, "Наружный угол") == 4  # 3 м стены — одна планка 3,05 на угол
    assert qty(est, "Стартовая") == math.ceil((36 - 0.9) * 1.05 / 3.66)
    rake = 4 * math.hypot(4, 2)
    assert qty(est, "J-профиль") == math.ceil(rake * 1.05 / 3.05)
    assert not any("Внутренний" in line.name for line in est.lines)


def test_hip_roof_has_no_gables(catalog):
    est = calculate(make_house(roof_type="hip", gable_height_m=2), catalog)
    assert est.gable_area == 0
    assert not any("J-профиль" in line.name for line in est.lines)


def test_tall_walls_need_two_corner_pieces(catalog):
    est = calculate(make_house(wall_height_m=5.5), catalog)
    assert qty(est, "Наружный угол") == 8


def test_total_is_sum(catalog):
    est = calculate(make_house(), catalog)
    assert est.total == sum(line.qty * line.price for line in est.lines)


def test_parse_openings():
    result = parse_openings("1,2х1,4х6; 0.6x0.6x2")
    assert [(o.width_m, o.height_m, o.count) for o in result] == [(1.2, 1.4, 6), (0.6, 0.6, 2)]
    assert parse_openings("0") == []
    with pytest.raises(InputError):
        parse_openings("1,2 на 1,4")


def test_parse_corners():
    assert parse_corners("4") == (4, 0)
    assert parse_corners("6 2") == (6, 2)


def test_first_dimension_scales_the_rest():
    confirmed: set[str] = set()
    house = set_dimension(make_house(), "length_m", 12.5, confirmed)  # ×1.25
    assert house.width_m == 10
    assert house.wall_height_m == 3.75
    assert house.gable_height_m == 2.5

    house = set_dimension(house, "width_m", 8, confirmed)  # ×0.8, только ширина и фронтон
    assert house.length_m == 12.5
    assert house.wall_height_m == 3.75
    assert house.gable_height_m == 2


def test_fasteners(catalog):
    est = calculate(make_house(), catalog)
    profiles = sum(line.qty for line in est.lines if line.unit == "шт" and "Панель" not in line.name)
    expected = math.ceil((est.net_area * 15 + profiles * 10) / 250)
    assert qty(est, "Саморезы") == expected
