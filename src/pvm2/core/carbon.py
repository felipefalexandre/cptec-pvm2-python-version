"""Carbon cycle of CPTEC-PVM2 (carbon1/carbon2 in carbon2.f).

The expressions, thresholds and operation order follow the legacy Fortran
implementation.  Every function is vectorised over an arbitrary spatial grid.
"""

from __future__ import annotations

import numpy as np

from .constants import MOL_TO_KGC, SECONDS_PER_YEAR, WMAX


def tetens(t):
    """Saturation vapour pressure (hPa) as in wbm4.f/tetens."""
    t = np.asarray(t)
    es_pos = 6.1078 * np.exp((7.5 * t / (237.3 + t)) * np.log(10.0))
    es_neg = 6.1078 * np.exp((9.5 * t / (265.5 + t)) * np.log(10.0))
    return np.where(t >= 0.0, es_pos, es_neg)


def _water_stress(wa):
    f5 = np.empty_like(wa)
    f5 = np.where(wa > 0.5, 1.0, f5)
    mid = (wa >= 0.205) & (wa <= 0.5)
    f5 = np.where(mid, (wa - 0.205) / (0.5 - 0.205), f5)
    f5 = np.where(wa < 0.205, wa, f5)
    return f5


def carbon1(temp, p0, w, wmax, ca, ipar, return_es=False):
    """Photosynthesis, autotrophic respiration and NPP (Eqs. 1-25).

    ``return_es`` appends the saturation vapour pressure already computed for
    the temperature term, so the water-balance routines can reuse it instead
    of evaluating ``tetens`` again for the same temperature.
    """
    temp = np.asarray(temp)
    p0 = np.asarray(p0)
    w = np.asarray(w)
    ipar = np.asarray(ipar)
    ca = np.asarray(ca)

    vm = (0.00004 * 2.0 ** (0.1 * (temp - 25.0))) / (
        1.0 + np.exp(0.3 * (temp - 36.0))
    )
    mgama = 21200.0 / (5200.0 * (0.57 ** (0.1 * (temp - 25.0))))
    f2 = 30.0 * (2.1 ** (0.1 * (temp - 25.0)))
    f3 = 30000.0 * (1.2 ** (0.1 * (temp - 25.0)))
    es = tetens(temp)
    rmax = 0.622 * (es / (p0 - es))
    r = (-0.315) * rmax

    k16 = 0.9
    k17 = 0.1
    ci = k16 * (1.0 - (r / k17)) * (ca - mgama) + mgama
    f10 = 1.23 / (1.0 + np.exp(-1.0 * (ca - 24.11) / 8.93))

    jc = vm * ((ci - mgama) / (ci + (f2 * f10 * (1.0 + (21200.0 / f3)))))
    jl = 0.08 * (1.0 - 0.15) * ipar * ((ci - mgama) / (ci + (2.0 * mgama)))
    je = 0.5 * vm

    a = 0.83
    b = -(jc + jl)
    c = jc * jl
    delta = b**2 - 4.0 * a * c
    jp1 = (-b - np.sqrt(delta)) / (2.0 * a)
    jp2 = (-b + np.sqrt(delta)) / (2.0 * a)
    jp = np.minimum(jp1, jp2)

    a2 = 0.93
    b2 = -(jp + je)
    c2 = jp * je
    delta2 = b2**2 - 4.0 * a2 * c2
    j1 = (-b2 - np.sqrt(delta2)) / (2.0 * a2)
    j2 = (-b2 + np.sqrt(delta2)) / (2.0 * a2)
    f1a = np.minimum(j1, j2)

    wa = w / wmax
    f5 = _water_stress(wa)

    in_window = (temp >= -10.0) & (temp <= 50.0)
    f1 = np.where(in_window, f1a * f5, 0.0)

    laia = 0.25 * np.exp(2.5 * (f1 / 0.000008))
    sunlai = (1.0 - np.exp(-0.5 * laia)) / 0.5
    shadelai = laia - sunlai
    f4 = (1.0 - np.exp(-0.5 * laia)) / 0.5
    f4sun = (1.0 - np.exp(-0.5 * sunlai)) / 0.5
    f4shade = (1.0 - np.exp(-1.5 * shadelai)) / 1.5

    ph = MOL_TO_KGC * SECONDS_PER_YEAR * f1 * f4sun * f4shade
    rl = MOL_TO_KGC * SECONDS_PER_YEAR * 0.015 * vm * f4 * f5
    rp = 3.85 * rl
    ar = np.where(in_window, rl + rp, 0.0)
    nppa = np.maximum(ph - ar, 0.0)
    if return_es:
        return ph, ar, nppa, laia, f5, es
    return ph, ar, nppa, laia, f5


def carbon2(tsoil, f5, evap, laia):
    """Litter, soil carbon and heterotrophic respiration (Eqs. 26-31)."""
    tsoil = np.asarray(tsoil)
    f5 = np.asarray(f5)
    evap = np.asarray(evap)
    laia = np.asarray(laia)

    f6 = 1.16 * 10.0 ** (-1.4553 + 0.0014175 * (evap * 365.0))
    f7 = 2.0 ** (0.1 * (tsoil - 25.0))
    lf = 0.1 * laia
    cl = lf / f6
    cs = ((0.3 * cl) / (0.05 * f7)) * f5
    in_window = (tsoil >= -10.0) & (tsoil <= 50.0)
    hr = 0.25 * (cl * (f6**2) + (cs * f5 * evap * (f7**2)))
    hr = np.where(in_window, hr, 0.0)
    return cl, cs, hr
