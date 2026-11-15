import numpy as np
import pytest

from pvm2.core import carbon


def test_carbon1_matches_fortran(fortran_scalars):
    for case in fortran_scalars["carbon1"]:
        ph, ar, npp, laia, f5 = carbon.carbon1(
            case["temp"],
            case["p0"],
            case["w"],
            case["wmax"],
            case["ca"],
            case["ipar"],
        )
        assert ph == pytest.approx(case["photo"], rel=1e-9, abs=1e-12)
        assert ar == pytest.approx(case["aresp"], rel=1e-9, abs=1e-12)
        assert npp == pytest.approx(case["npp"], rel=1e-9, abs=1e-12)
        assert laia == pytest.approx(case["laia"], rel=1e-9, abs=1e-12)
        assert f5 == pytest.approx(case["f5"], rel=1e-9, abs=1e-12)


def test_carbon2_matches_fortran(fortran_scalars):
    for case in fortran_scalars["carbon2"]:
        cl, cs, hr = carbon.carbon2(
            case["tsoil"], case["f5"], case["evap"], case["laia"]
        )
        assert cl == pytest.approx(case["cl"], rel=1e-9, abs=1e-12)
        assert cs == pytest.approx(case["cs"], rel=1e-9, abs=1e-12)
        assert hr == pytest.approx(case["hresp"], rel=1e-9, abs=1e-12)


def test_carbon_functions_are_vectorised():
    temp = np.array([-20.0, 0.0, 25.0, 40.0])
    ph, ar, npp, laia, f5 = carbon.carbon1(
        temp, np.full(4, 1000.0), np.full(4, 250.0), 500.0, 35.35, 150.0
    )
    assert ph.shape == temp.shape
    assert np.all(npp >= 0.0)
    assert np.all(np.isfinite(ph))
