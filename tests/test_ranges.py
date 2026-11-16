import numpy as np
import pytest

from pvm2 import ranges


def test_plausible_values_pass():
    ranges.check_field("precipitation", np.array([0.0, 200.0]), "test")
    ranges.check_field("temperature", np.array([-30.0, 30.0]), "test")
    ranges.check_field("par", np.array([0.0, 200.0]), "test")
    ranges.check_field("pressure", np.array([500.0, 1013.0]), "test")
    ranges.check_field("uwind", np.array([-20.0, 20.0]), "test")
    ranges.check_field("landmask", np.array([0.0, 1.0]), "test")


def test_kelvin_temperature_with_wrong_units_is_rejected():
    with pytest.raises(ValueError, match="temperature"):
        ranges.check_field("temperature", np.array([273.15]), "test")


def test_pressure_in_pa_is_rejected():
    with pytest.raises(ValueError, match="pressure"):
        ranges.check_field("pressure", np.array([101325.0]), "test")


def test_fractional_landmask_is_rejected():
    with pytest.raises(ValueError, match="landmask"):
        ranges.check_field("landmask", np.array([0.0, 0.5, 1.0]), "test")


def test_check_inputs_reports_multiple_problems():
    data = {
        "precipitation": np.array([-10.0]),
        "temperature": np.array([300.0]),
        "par": np.array([2000.0]),
        "pressure": np.array([101325.0]),
        "uwind": np.array([0.0]),
        "landmask": np.array([1.0]),
    }
    with pytest.raises(ValueError) as excinfo:
        ranges.check_inputs(data, "test")
    message = str(excinfo.value)
    for key in ("precipitation", "temperature", "par", "pressure"):
        assert key in message
