import numpy as np
import pytest

from pvm2 import grid


def _preset(resolution, lat, lon):
    return grid.LandmaskPreset(
        name=f"test_{resolution}",
        resolution=resolution,
        description="test",
        lat=np.asarray(lat, dtype=np.float64),
        lon=np.asarray(lon, dtype=np.float64),
        landmask=np.ones((len(lat), len(lon)), dtype=np.int8),
    )


def test_axis_spacing_uses_largest_gap():
    values = np.array([0.0, 1.0, 2.0, 4.0])
    assert grid.axis_spacing(values) == 2.0


def test_compatible_presets_are_coarse_to_fine_without_upscaling():
    presets = [
        _preset(0.1, [0, 1], [0, 1]),
        _preset(0.5, [0, 1], [0, 1]),
        _preset(1.0, [0, 1], [0, 1]),
        _preset(2.5, [0, 1], [0, 1]),
    ]
    options = grid.compatible_presets(1.0, presets)
    assert [item.resolution for item in options] == [2.5, 1.0]
    assert grid.coarsest_compatible(1.0, presets).resolution == 1.0


def test_resample_constant_and_linear_field():
    source_lat = np.array([0.0, 1.0, 2.0])
    source_lon = np.array([0.0, 1.0, 2.0])
    target_lat = np.array([0.5, 1.5])
    target_lon = np.array([0.5, 1.5])
    values = source_lat[:, None] + source_lon[None, :]
    out = grid.resample_field(
        values,
        source_lat,
        source_lon,
        target_lat,
        target_lon,
        periodic_lon=False,
    )
    expected = target_lat[:, None] + target_lon[None, :]
    assert np.allclose(out, expected)


def test_resample_accepts_0_360_source_and_180_target():
    source_lat = np.array([-45.0, 45.0])
    source_lon = np.array([0.0, 90.0, 180.0, 270.0])
    target_lat = np.array([-45.0, 45.0])
    target_lon = np.array([-180.0, -90.0, 0.0, 90.0])
    values = np.tile(
        np.array([10.0, 20.0, 30.0, 40.0]), (2, 1)
    )
    out = grid.resample_field(
        values, source_lat, source_lon, target_lat, target_lon
    )
    expected = np.tile(
        np.array([30.0, 40.0, 10.0, 20.0]), (2, 1)
    )
    assert np.allclose(out, expected)


def test_resample_regional_grid_across_dateline():
    source_lat = np.array([0.0, 1.0])
    source_lon = np.array([350.0, 355.0, 0.0, 5.0])
    target_lat = np.array([0.5])
    target_lon = np.array([-5.0, 0.0])
    values = np.tile(np.array([1.0, 2.0, 3.0, 4.0]), (2, 1))
    out = grid.resample_field(
        values,
        source_lat,
        source_lon,
        target_lat,
        target_lon,
        periodic_lon=False,
    )
    assert np.allclose(out, [[2.0, 3.0]])


def test_resample_preserves_nan_only_when_all_corners_are_missing():
    source_lat = np.array([0.0, 1.0])
    source_lon = np.array([0.0, 1.0])
    values = np.array([[np.nan, 2.0], [4.0, 6.0]])
    out = grid.resample_field(
        values,
        source_lat,
        source_lon,
        np.array([0.5]),
        np.array([0.5]),
        periodic_lon=False,
    )
    assert np.allclose(out, [[4.0]])


def test_bundled_presets_are_binary_and_global():
    presets = grid.available_presets()
    resolutions = {item.resolution for item in presets}
    assert {0.1, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0} <= resolutions
    for preset in presets:
        assert set(np.unique(preset.landmask)) <= {-1, 0, 1}
        assert np.all(np.diff(preset.lat) > 0)
        assert np.all(np.diff(preset.lon) > 0)
def test_hemisphere_longitude_is_not_global():
    lon = np.arange(0.0, 180.0, 1.0)
    assert grid._is_global_longitude(lon) is False


def test_360_longitude_is_global():
    lon = np.arange(0.0, 360.0, 1.0)
    assert grid._is_global_longitude(lon) is True

def test_resample_regional_0_360_source_to_180_target():
    source_lat = np.array([0.0, 1.0])
    source_lon = np.array([300.0, 305.0, 310.0, 315.0])
    target_lat = np.array([0.5])
    target_lon = np.array([-60.0, -55.0])
    values = np.tile(np.array([30.0, 30.5, 31.0, 31.5]), (2, 1))
    out = grid.resample_field(
        values,
        source_lat,
        source_lon,
        target_lat,
        target_lon,
        periodic_lon=False,
    )
    assert np.allclose(out, [[30.0, 30.5]])
