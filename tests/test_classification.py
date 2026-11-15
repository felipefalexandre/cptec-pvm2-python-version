import numpy as np
import pytest

from pvm2.core import water_balance as wb


def _classify_one(tmin, ratio, seanpp=0.5, avgpar=80.0, fire=False):
    shape = (1, 1)
    meanpp = ratio * max((avgpar - 35.0) / 45.0, 0.0)
    wsoil2 = np.full((12,) + shape, 0.5)
    uwind = np.full((12,) + shape, 2.0)
    bpot, _, _, _ = wb.classify(
        np.full(shape, 1000.0),
        np.ones(shape),
        np.full(shape, tmin),
        np.full(shape, meanpp),
        np.full(shape, seanpp),
        np.full(shape, avgpar),
        wsoil2,
        uwind,
        fire=fire,
    )
    return int(bpot[0, 0])


def test_ocean_is_zero():
    shape = (1, 1)
    bpot, _, _, _ = wb.classify(
        np.full(shape, 1000.0),
        np.zeros(shape),
        np.full(shape, 20.0),
        np.full(shape, 100.0),
        np.full(shape, 0.5),
        np.full(shape, 100.0),
        np.full((12,) + shape, 0.5),
        np.full(shape, 2.0),
    )
    assert bpot[0, 0] == 0.0


@pytest.mark.parametrize(
    "tmin,rot,seanpp,avgpar,expected",
    [
        (-35.0, 0.0, 0.5, 80.0, 20),
        (-35.0, 0.1, 0.5, 80.0, 10),
        (-35.0, 0.6, 0.5, 80.0, 5),
        (-20.0, 0.05, 0.5, 80.0, 10),
        (-20.0, 0.5, 0.5, 50.0, 4),
        (-20.0, 0.5, 0.5, 100.0, 7),
        (-10.0, 0.02, 0.5, 80.0, 11),
        (-10.0, 0.20, 0.5, 80.0, 9),
        (-7.0, 0.4, 0.5, 80.0, 7),
        (-7.0, 0.6, 0.5, 80.0, 3),
        (0.0, 0.6, 0.5, 80.0, 7),
        (0.0, 0.8, 0.5, 80.0, 2),
        (20.0, 0.003, 0.5, 80.0, 11),
        (20.0, 0.10, 0.5, 80.0, 9),
        (20.0, 0.5, 0.05, 80.0, 13),
        (20.0, 0.9, 0.05, 80.0, 1),
        (20.0, 0.5, 0.5, 80.0, 6),
    ],
)
def test_biome_rules(tmin, rot, seanpp, avgpar, expected):
    assert _classify_one(tmin, rot, seanpp, avgpar) == expected


def test_fire_parameterisation_only_changes_savanna():
    changed = 0
    for uwind in (0.5, 2.0):
        shape = (1, 1)
        meanpp = 0.5 * max((80.0 - 35.0) / 45.0, 0.0)
        args = (
            np.full(shape, 1000.0),
            np.ones(shape),
            np.full(shape, 20.0),
            np.full(shape, meanpp),
            np.full(shape, 0.5),
            np.full(shape, 80.0),
            np.full((12,) + shape, 0.5),
            np.full((12,) + shape, uwind),
        )
        with_fire, _, _, _ = wb.classify(*args, fire=True)
        no_fire, _, _, _ = wb.classify(*args, fire=False)
        assert no_fire[0, 0] == 6.0
        changed += int(with_fire[0, 0] != no_fire[0, 0])
    assert changed == 1


def test_transition_month_detects_dry_to_wet():
    wsoil2 = np.zeros((12, 1, 1))
    wsoil2[:, 0, 0] = [0.8, 0.7, 0.1, 0.6, 0.8, 0.9, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
    month = wb._find_transition_month(wsoil2)
    assert month[0, 0] == 2


def test_budget_month_conserves_bounds():
    out = wb.budget_month(
        0,
        np.array([0.01]),
        np.array([0.0]),
        np.array([0.0]),
        np.array([20.0]),
        np.array([20.0]),
        np.array([100.0]),
        np.array([1000.0]),
        np.array([3.0]),
        35.35,
        np.array([150.0]),
    )
    for key in ("w", "g", "s", "photo", "aresp", "npp"):
        assert np.all(np.isfinite(out[key]))
        assert out[key].shape == (1,)
    assert 0.0 <= out["w"][0] <= wb.WMAX
    assert 0.0 <= out["g"][0] <= wb.WMAX
    assert out["s"][0] >= 0.0
    assert out["npp"][0] >= 0.0
