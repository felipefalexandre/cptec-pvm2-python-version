"""Water balance and environmental diagnostics of CPTEC-PVM2 (wbm4.f).

The model is integrated cell by cell in the legacy code.  Here the same
time-stepping is performed simultaneously for every grid cell, without
changing the order of operations inside a day or a month.
"""

from __future__ import annotations

import numpy as np

from .carbon import carbon1, carbon2, tetens
from .constants import (
    AE_INTERCEPT,
    AE_SLOPE,
    H5,
    MONTH_DAYS,
    RA,
    RCMIN,
    RH,
    SOIL_TAU_MONTHS,
    TICE,
    TSNOW,
    UNDEF,
    WMAX,
)
from . import checkpoint as checkpoint_module
from . import constants


def runoff(w, wmax):
    """Soil-moisture runoff (Eq. 10, NCEP-NCAR recalibration)."""
    return 11.5 * ((w / wmax) ** 6.6)


def potential_evapotranspiration(spre, temp, ur, rn, rc, es=None):
    """Penman potential evapotranspiration with fixed stomatal resistance."""
    es1 = tetens(temp + 1.0)
    es2 = tetens(temp - 1.0)
    delta = (es1 - es2) / ((temp + 1.0) - (temp - 1.0))
    if es is None:
        es = tetens(temp)
    delta_e = es * (1.0 - ur)
    gama = spre * 1004.0 / (2.45e6 * 0.622)
    gama2 = gama * (RA + rc) / RA
    evap = (delta * rn + (1.20 * 1004.0 / RA) * delta_e) / (delta + gama2)
    evap = evap * (86400.0 / 2.45e6)
    return np.maximum(evap, 0.0)


def penman(spre, temp, w, wmax, ur, rn, rc2, es=None):
    """Actual evapotranspiration (Eq. 32), including the legacy dual test."""
    es1 = tetens(temp + 1.0)
    es2 = tetens(temp - 1.0)
    delta = (es1 - es2) / ((temp + 1.0) - (temp - 1.0))
    if es is None:
        es = tetens(temp)
    delta_e = es * (1.0 - ur)

    zero = np.zeros_like(np.asarray(delta_e))
    threshold = (1.0 / H5) - 0.5

    evap = zero
    cond_zero = (delta_e >= threshold) | (rc2 >= 4500.0)
    evap = np.where(cond_zero, 0.0, evap)

    gama = spre * 1004.0 / (2.45e6 * 0.622)
    gama2 = gama * (RA + rc2) / RA
    evap_calc = (delta * rn + (1.20 * 1004.0 / RA) * delta_e) / (delta + gama2)
    evap_calc = evap_calc * (86400.0 / 2.45e6)
    evap_calc = np.maximum(evap_calc, 0.0)
    cond_calc = (delta_e < threshold) | (rc2 < 4500.0)
    return np.where(cond_calc, evap_calc, evap)


def budget_month(
    month_index,
    w1,
    g1,
    s1,
    tsoil,
    temp,
    prec,
    p0,
    ae,
    ca,
    ipar,
):
    """Integrate one month for an arbitrary number of grid cells.

    Parameters are arrays over the grid; ``month_index`` is 0-based.
    Returns final storages and monthly/annualised carbon and water fluxes.
    """
    ndays = MONTH_DAYS[month_index]
    temp = np.asarray(temp)
    prec = np.asarray(prec)
    w = np.array(w1, copy=True)
    g = np.array(g1, copy=True)
    s = np.array(s1, copy=True)

    shape = np.shape(temp)
    smavg = np.zeros(shape)
    ruavg = np.zeros(shape)
    evavg = np.zeros(shape)
    epavg = np.zeros(shape)
    rcavg = np.zeros(shape)
    laiavg = np.zeros(shape)
    phavg = np.zeros(shape)
    aravg = np.zeros(shape)
    nppavg = np.zeros(shape)
    clavg = np.zeros(shape)
    csavg = np.zeros(shape)
    hravg = np.zeros(shape)

    psnow = np.where(temp < TSNOW, prec / float(ndays), 0.0)
    prain = np.where(temp < TSNOW, 0.0, prec / float(ndays))

    for _ in range(ndays):
        ph, ar, nppa, laia, f5, es = carbon1(
            temp, p0, w, WMAX, ca, ipar, return_es=True
        )
        emax = potential_evapotranspiration(p0, temp, RH, ae, RCMIN, es=es)

        smelt = 2.63 + 2.55 * temp + 0.0912 * temp * prain
        smelt = np.maximum(smelt, 0.0)
        smelt = np.minimum(smelt, s + psnow)
        s = s + (psnow - smelt)

        frozen = tsoil <= TICE
        g_frozen = g + w
        w_frozen = np.zeros_like(w)
        roff_frozen = smelt + prain
        rc_frozen = np.full(shape, 100.0)

        nppb = np.maximum(nppa, 0.05)
        rc2 = ca / (0.9 * (nppb * 2.64e-6) * 0.685 * (p0 * 100.0))

        w_thaw = w + g
        g_thaw = np.zeros_like(g)
        rimelt = np.zeros_like(w)
        over = w_thaw > WMAX
        rimelt = np.where(over, w_thaw - WMAX, rimelt)
        w_thaw = np.where(over, WMAX, w_thaw)
        roff = runoff(w_thaw, WMAX)
        evap = penman(p0, temp, w_thaw, WMAX, RH, ae, rc2, es=es)
        dw = prain + smelt - evap - roff
        w_new = w_thaw + dw
        over2 = w_new > WMAX
        roff = np.where(over2, roff + (w_new - WMAX), roff)
        w_new = np.where(over2, WMAX, w_new)
        w_new = np.where(w_new < 0.0, 0.0, w_new)
        roff = roff + rimelt
        cl, cs, hr = carbon2(tsoil, f5, evap, laia)

        w = np.where(frozen, w_frozen, w_new)
        g = np.where(frozen, g_frozen, g_thaw)
        roff = np.where(frozen, roff_frozen, roff)
        evap = np.where(frozen, 0.0, evap)
        rc2 = np.where(frozen, rc_frozen, rc2)
        ph = np.where(frozen, 0.0, ph)
        ar = np.where(frozen, 0.0, ar)
        nppa = np.where(frozen, 0.0, nppa)
        laia = np.where(frozen, 0.0, laia)
        cl = np.where(frozen, 0.0, cl)
        cs = np.where(frozen, 0.0, cs)
        hr = np.where(frozen, 0.0, hr)

        smavg = smavg + smelt
        ruavg = ruavg + roff
        evavg = evavg + evap
        epavg = epavg + emax
        rcavg = rcavg + rc2
        phavg = phavg + ph / 365.0
        aravg = aravg + ar / 365.0
        nppavg = nppavg + nppa / 365.0
        laiavg = laiavg + laia / 365.0
        clavg = clavg + cl / 365.0
        csavg = csavg + cs / 365.0
        hravg = hravg + hr / 365.0

    inv_days = 1.0 / float(ndays)
    return {
        "w": w,
        "g": g,
        "s": s,
        "snowmelt": smavg * inv_days,
        "runoff": ruavg * inv_days,
        "evap": evavg * inv_days,
        "evap_pot": epavg * inv_days,
        "rc": rcavg * inv_days,
        "photo": phavg * 12.0,
        "aresp": aravg * 12.0,
        "npp": nppavg * 12.0,
        "lai": laiavg * 12.0,
        "litter": clavg * 12.0,
        "csoil": csavg * 12.0,
        "hresp": hravg * 12.0,
    }


_MONTH_FIELDS = {
    "wsoil": "w",
    "gsoil": "g",
    "ssoil": "s",
    "snowmelt": "snowmelt",
    "runoff": "runoff",
    "evap": "evap",
    "evap_pot": "evap_pot",
    "rc": "rc",
    "lai": "lai",
    "photo": "photo",
    "aresp": "aresp",
    "npp": "npp",
    "litter": "litter",
    "csoil": "csoil",
    "hresp": "hresp",
}

def soil_temperature(temp, land):
    """Equilibrium soil temperature for every land cell (1200-month spin-up)."""
    shape = temp.shape[1:]
    tsoil = np.full((12,) + shape, UNDEF)
    t0 = np.zeros(shape)
    decay = np.exp(-1.0 / SOIL_TAU_MONTHS)
    for n in range(1, 1201):
        k = (n - 1) % 12
        t1 = t0 * decay + (1.0 - decay) * temp[k]
        tsoil[k] = np.where(land, (t0 + t1) / 2.0, UNDEF)
        t0 = np.where(land, t1, t0)
    return tsoil


def _find_transition_month(wsoil2):
    """Vectorised equivalent of findm for every grid cell."""
    nt, ny, nx = wsoil2.shape
    w = np.moveaxis(wsoil2, 0, -1).reshape(-1, 12).astype(np.float64)
    w2 = w.copy()
    wmax = w.max(axis=1)
    wmin = w.min(axis=1)
    wlim = (wmax - wmin) / 8.0

    months = np.zeros((w.shape[0], 12), dtype=np.int64)
    slopes = np.zeros((w.shape[0], 12), dtype=np.float64)
    for it in range(12):
        mmin = np.argmin(w2, axis=1)
        months[:, it] = mmin
        nxt = np.where(mmin == 11, 0, mmin + 1)
        slopes[:, it] = w[np.arange(w.shape[0]), nxt] - w[np.arange(w.shape[0]), mmin]
        w2[np.arange(w.shape[0]), mmin] = 100.0

    found = np.zeros(w.shape[0], dtype=bool)
    chosen = np.full(w.shape[0], -1, dtype=np.int64)
    for it in range(12):
        take = (~found) & (slopes[:, it] >= wlim)
        chosen[take] = months[take, it]
        found |= take
    if not np.all(found):
        bad = np.flatnonzero(~found)
        raise RuntimeError(
            "findm: no dry-to-wet transition found for "
            f"{bad.size} cell(s); legacy code would read outside dw[12]"
        )
    return chosen.reshape(ny, nx)


def _iter_chunks(indices, size):
    if size is None or indices.size <= size:
        yield indices
        return
    for start in range(0, indices.size, size):
        yield indices[start : start + size]


def environmental_variables(
    prec,
    temp,
    lsmk,
    p0,
    ca,
    par,
    max_years=20000,
    progress=None,
    tile_cells=None,
    checkpoint_path=None,
    resume=False,
    checkpoint_every=1,
):
    """Run the full water balance and derive the environmental variables.

    Parameters are arrays shaped (12, ny, nx) except ``lsmk``, ``p0`` and
    ``ca``.  Returns the nine variables written by env5.f plus monthly fields.
    ``progress`` is an optional callable receiving one event dictionary per
    integrated month, plus a final event with ``done=True``.  ``tile_cells``
    limits the number of active cells processed at once without changing the
    result; ``checkpoint_path``/``resume`` persist and restore the equilibrium
    state after complete model years.
    """
    prec = np.asarray(prec)
    temp = np.asarray(temp)
    lsmk = np.asarray(lsmk)
    p0 = np.asarray(p0)
    par = np.asarray(par)

    nt, ny, nx = prec.shape
    if nt != 12:
        raise ValueError(f"expected 12 months, got {nt}")
    land = lsmk.astype(np.int32) != 0
    shape = (ny, nx)

    tsoil = soil_temperature(temp, land)

    fields = {
        "wsoil": np.full((12,) + shape, UNDEF),
        "gsoil": np.full((12,) + shape, UNDEF),
        "ssoil": np.full((12,) + shape, UNDEF),
        "snowmelt": np.full((12,) + shape, UNDEF),
        "runoff": np.full((12,) + shape, UNDEF),
        "evap": np.full((12,) + shape, UNDEF),
        "evap_pot": np.full((12,) + shape, UNDEF),
        "rc": np.full((12,) + shape, UNDEF),
        "lai": np.full((12,) + shape, UNDEF),
        "photo": np.full((12,) + shape, UNDEF),
        "aresp": np.full((12,) + shape, UNDEF),
        "npp": np.full((12,) + shape, UNDEF),
        "litter": np.full((12,) + shape, UNDEF),
        "csoil": np.full((12,) + shape, UNDEF),
        "hresp": np.full((12,) + shape, UNDEF),
    }

    ncell = int(np.prod(shape))
    temp_f = temp.reshape(12, ncell)
    prec_f = prec.reshape(12, ncell)
    par_f = par.reshape(12, ncell)
    tsoil_f = tsoil.reshape(12, ncell)
    p0_f = p0.reshape(ncell)
    fields_f = {name: values.reshape(12, ncell) for name, values in fields.items()}

    if tile_cells is not None and tile_cells <= 0:
        raise ValueError("tile_cells must be positive or None")
    if checkpoint_every <= 0:
        raise ValueError("checkpoint_every must be positive")
    if resume and not checkpoint_path:
        raise ValueError("resume requires a checkpoint path")

    w = np.full(ncell, 0.01)
    g = np.zeros(ncell)
    s = np.zeros(ncell)
    wg0 = np.full((12, ncell), -1.0)
    active = np.flatnonzero(land.reshape(ncell))
    land_cells = int(active.size)
    year = 0

    checkpoint_meta = None
    if checkpoint_path or resume:
        checkpoint_meta = {
            "format_version": checkpoint_module.FORMAT_VERSION,
            "shape": [int(ny), int(nx)],
            "co2_pa": float(ca),
            "input_sha256": checkpoint_module.input_digest(
                {
                    "precipitation": prec,
                    "temperature": temp,
                    "par": par,
                    "pressure": p0,
                    "landmask": lsmk,
                }
            ),
        }
    if resume:
        saved = checkpoint_module.load(
            checkpoint_path,
            fields,
            checkpoint_meta,
        )
        year = saved["year"]
        w = saved["w"]
        g = saved["g"]
        s = saved["s"]
        wg0 = saved["wg0"]
        active = saved["active"]
        for name, values in saved["fields"].items():
            fields[name][...] = values

    if progress is not None:
        progress(
            {
                "phase": "equilibrium",
                "year": year,
                "month": 0,
                "active_cells": int(active.size),
                "land_cells": land_cells,
                "done": False,
            }
        )
    while active.size:
        year += 1
        if year > max_years:
            raise RuntimeError(
                f"water balance did not reach equilibrium after {max_years} years "
                f"for {active.size} cell(s)"
            )
        for k in range(12):
            if active.size == 0:
                break
            for cells in _iter_chunks(active, tile_cells):
                ae = AE_SLOPE * temp_f[k, cells] + AE_INTERCEPT
                out = budget_month(
                    k,
                    w[cells],
                    g[cells],
                    s[cells],
                    tsoil_f[k, cells],
                    temp_f[k, cells],
                    prec_f[k, cells],
                    p0_f[cells],
                    ae,
                    ca,
                    par_f[k, cells],
                )
                for field_name, out_name in _MONTH_FIELDS.items():
                    fields_f[field_name][k, cells] = out[out_name]
                w[cells] = out["w"]
                g[cells] = out["g"]
                s[cells] = out["s"]
            if progress is not None:
                progress(
                    {
                        "phase": "equilibrium",
                        "year": year,
                        "month": k + 1,
                        "active_cells": int(active.size),
                        "land_cells": land_cells,
                        "done": False,
                    }
                )

        remaining = []
        for cells in _iter_chunks(active, tile_cells):
            wsoil_a = fields_f["wsoil"][:, cells]
            gsoil_a = fields_f["gsoil"][:, cells]
            dwww = (wsoil_a + gsoil_a - wg0[:, cells]) / WMAX
            converged = np.sum(np.abs(dwww) > 0.001, axis=0) == 0
            if np.any(converged):
                keep = cells[~converged]
                if keep.size:
                    wg0[:, keep] = wsoil_a[:, ~converged] + gsoil_a[:, ~converged]
                    remaining.append(keep)
            else:
                wg0[:, cells] = wsoil_a + gsoil_a
                remaining.append(cells)
        active = (
            np.concatenate(remaining)
            if remaining
            else np.empty(0, dtype=np.int64)
        )
        if (
            checkpoint_path
            and (active.size == 0 or year % checkpoint_every == 0)
        ):
            checkpoint_module.save(
                checkpoint_path,
                year=year,
                w=w,
                g=g,
                s=s,
                wg0=wg0,
                active=active,
                fields=fields,
                meta=checkpoint_meta,
            )
    if progress is not None:
        progress(
            {
                "phase": "equilibrium",
                "year": year,
                "month": 12,
                "active_cells": 0,
                "land_cells": land_cells,
                "done": True,
            }
        )
    tmin = np.min(temp, axis=0)
    npp = fields["npp"]
    meanpp = np.sum(npp / 12.0, axis=0)
    mphoto = np.sum(fields["photo"] / 12.0, axis=0)
    maresp = np.sum(fields["aresp"] / 12.0, axis=0)
    meanhr = np.sum(fields["hresp"] / 12.0, axis=0)
    meancs = np.sum(fields["csoil"] / 12.0, axis=0)
    nppmin = np.min(npp, axis=0)
    nppmax = np.max(npp, axis=0)

    seai_acc = np.zeros(shape)
    for k in range(12):
        seai_acc = np.where(
            fields["wsoil"][k] / WMAX < 0.5,
            seai_acc + (0.5 - fields["wsoil"][k] / WMAX),
            seai_acc,
        )
    seai = 1.0 - seai_acc / 6.0

    etpot = np.zeros(shape)
    ereal = np.zeros(shape)
    for k in range(12):
        usable = fields["gsoil"][k] / WMAX < 1.0e-7
        etpot = np.where(usable, etpot + fields["evap_pot"][k], etpot)
        ereal = np.where(usable, ereal + fields["evap"][k], ereal)
    weti_ratio = np.divide(
        ereal, etpot, out=np.zeros(shape), where=np.abs(etpot) >= 1.0e-5
    )
    weti = np.where(np.abs(etpot) < 1.0e-5, 0.0, np.minimum(weti_ratio, 1.0))

    seanpp_raw = np.where(
        meanpp > 0.0,
        (nppmax - nppmin) / np.where(meanpp != 0.0, meanpp, 1.0),
        nppmax - nppmin,
    )
    auxs = np.max(seanpp_raw[land]) if np.any(land) else -100.0
    seanpp = np.where(land, seanpp_raw / auxs, UNDEF)

    ice_any = np.any(fields["gsoil"] / WMAX > 1.0e-7, axis=0)
    wsoil2 = np.full((12,) + shape, UNDEF)
    for k in range(12):
        wsoil2[k] = np.where(
            land & ~ice_any, fields["wsoil"][k] / WMAX, UNDEF
        )

    out = {
        "tmin": np.where(land, tmin, UNDEF),
        "meanpp": np.where(land, meanpp, UNDEF),
        "seanpp": seanpp,
        "meanhr": np.where(land, meanhr, UNDEF),
        "meancs": np.where(land, meancs, UNDEF),
        "mphoto": np.where(land, mphoto, UNDEF),
        "maresp": np.where(land, maresp, UNDEF),
        "seai": np.where(land, seai, UNDEF),
        "weti": np.where(land, weti, UNDEF),
        "wsoil2": wsoil2,
        "evaptr": fields["evap"],
        "mnpp": fields["npp"],
        "photo": fields["photo"],
        "aresp": fields["aresp"],
        "rc": fields["rc"],
        "wsoil": fields["wsoil"],
        "gsoil": fields["gsoil"],
        "ssoil": fields["ssoil"],
        "snowmelt": fields["snowmelt"],
        "runoff": fields["runoff"],
        "evap_pot": fields["evap_pot"],
        "lai": fields["lai"],
        "litter": fields["litter"],
        "csoil": fields["csoil"],
        "hresp": fields["hresp"],
        "equilibrium_years": year,
        "auxs": auxs,
    }
    out["_tsoil"] = tsoil
    return out


def classify(p0, lsmk, tmin, meanpp, seanpp, avgpar, wsoil2, uwind, fire=True):
    """Biome allocation of pvm5.f, including the U-wind fire parameterisation."""
    tmin = np.asarray(tmin)
    meanpp = np.asarray(meanpp)
    seanpp = np.asarray(seanpp)
    avgpar = np.asarray(avgpar)
    lsmk = np.asarray(lsmk)

    land = lsmk.astype(np.int32) != 0
    bpot = np.where(land, -1.0, 0.0)
    ratio = npp_par_ratio(meanpp, avgpar)

    desert_extratropical = (
        (tmin >= -15.0)
        & (tmin <= 10.0)
        & (ratio <= 0.05)
    )
    semi_extratropical = (
        (tmin >= -15.0)
        & (tmin <= 10.0)
        & ~(ratio <= 0.05)
        & (ratio <= 0.28)
    )
    desert_tropical = (tmin > 10.0) & (ratio <= 0.005)
    semi_tropical = (tmin > 10.0) & ~(ratio <= 0.005) & (ratio <= 0.15)
    bpot = np.where(desert_extratropical | desert_tropical, 11.0, bpot)
    bpot = np.where(semi_extratropical | semi_tropical, 9.0, bpot)

    remaining = bpot == -1.0

    ice = remaining & (tmin <= -27.0) & (ratio == 0.0)
    tundra_cold = remaining & (tmin <= -27.0) & (ratio != 0.0) & (ratio <= 0.3)
    larch = remaining & (tmin <= -27.0) & (ratio != 0.0) & ~(ratio <= 0.3)
    bpot = np.where(ice, 20.0, bpot)
    bpot = np.where(tundra_cold, 10.0, bpot)
    bpot = np.where(larch, 5.0, bpot)
    remaining = bpot == -1.0

    borealtundra = remaining & (tmin > -27.0) & (tmin <= -9.0) & (ratio <= 0.08)
    borealforest = (
        remaining & (tmin > -27.0) & (tmin <= -9.0) & ~(ratio <= 0.08) & (avgpar <= 58.0)
    )
    borealgrass = (
        remaining & (tmin > -27.0) & (tmin <= -9.0) & ~(ratio <= 0.08) & ~(avgpar <= 58.0)
    )
    bpot = np.where(borealtundra, 10.0, bpot)
    bpot = np.where(borealforest, 4.0, bpot)
    bpot = np.where(borealgrass, 7.0, bpot)
    remaining = bpot == -1.0

    mixedgrass = remaining & (tmin > -9.0) & (tmin <= -6.0) & (ratio <= 0.5)
    mixedforest = remaining & (tmin > -9.0) & (tmin <= -6.0) & ~(ratio <= 0.5)
    bpot = np.where(mixedgrass, 7.0, bpot)
    bpot = np.where(mixedforest, 3.0, bpot)
    remaining = bpot == -1.0

    tempgrass = remaining & (tmin > -6.0) & (tmin <= 10.0) & (ratio <= 0.7)
    tempforest = remaining & (tmin > -6.0) & (tmin <= 10.0) & ~(ratio <= 0.7)
    bpot = np.where(tempgrass, 7.0, bpot)
    bpot = np.where(tempforest, 2.0, bpot)
    remaining = bpot == -1.0

    caatinga = remaining & (tmin > 10.0) & (seanpp > 0.1) & (ratio <= 0.38)
    savanna = remaining & (tmin > 10.0) & (seanpp > 0.1) & ~(ratio <= 0.38)
    seasonal = remaining & (tmin > 10.0) & ~(seanpp > 0.1) & (ratio <= 0.72)
    ombroph = remaining & (tmin > 10.0) & ~(seanpp > 0.1) & ~(ratio <= 0.72)
    bpot = np.where(caatinga, 8.0, bpot)
    bpot = np.where(savanna, 6.0, bpot)
    bpot = np.where(seasonal, 13.0, bpot)
    bpot = np.where(ombroph, 1.0, bpot)

    if np.any(land & (bpot == -1.0)):
        raise RuntimeError("no biome assigned to one or more land grid cells")

    d2wm, ud2w = transition_and_wind(wsoil2, uwind, land)
    if fire:
        fire_keep = (bpot.astype(np.int32) == 6) & (ud2w <= 1.5)
        no_fire = (bpot.astype(np.int32) == 6) & ~(ud2w <= 1.5)
        bpot = np.where(no_fire, 13.0, bpot)
        bpot = np.where(fire_keep, 6.0, bpot)

    bpot = np.where(land, bpot, 0.0)
    ratio = np.where(land, ratio, 0.0)
    d2wm = np.where(land, d2wm, UNDEF)
    ud2w = np.where(land, ud2w, UNDEF)
    return bpot, ratio, d2wm, ud2w


def npp_par_ratio(anpp, apar):
    """NPP/IPAR ratio with the IPAR reference of pvm5.f (Eq. in ratio())."""
    refval = np.maximum((np.asarray(apar) - 35.0) / 45.0, 0.0)
    ratio = np.where(refval != 0.0, np.asarray(anpp) / np.where(refval != 0.0, refval, 1.0), 0.0)
    ratio = np.maximum(ratio, 0.0)
    ratio = np.minimum(ratio, 1.0)
    return np.where(refval != 0.0, ratio, 0.0)


def transition_and_wind(wsoil2, uwind, land):
    """Dry-to-wet transition month and the U-wind of the following month."""
    d2wm = np.full(land.shape, UNDEF)
    ud2w = np.full(land.shape, UNDEF)
    valid = land & (wsoil2[0] >= 0.0)
    if not np.any(valid):
        return d2wm, ud2w
    w = np.where(valid[None, :, :], wsoil2, 0.0)
    month = _find_transition_month(w)
    mr = np.where(month == 11, 0, month + 1)
    for k in range(12):
        take = valid & (mr == k)
        ud2w = np.where(take, uwind[k], ud2w)
    d2wm = np.where(valid, (month + 1).astype(np.float64), d2wm)
    return d2wm, ud2w


def potential_vegetation(
    prec,
    temp,
    ipar_wm2,
    lsmk,
    p0,
    ca,
    uwind,
    fire=True,
    max_years=20000,
    progress=None,
    tile_cells=None,
    checkpoint_path=None,
    resume=False,
    checkpoint_every=1,
):
    """End-to-end CPTEC-PVM2: climate -> environmental fields -> biomes."""
    par = np.asarray(ipar_wm2) / constants.IPAR_TO_EINSTEIN
    prec = np.maximum(np.asarray(prec), 0.0)
    env = environmental_variables(
        prec,
        temp,
        lsmk,
        p0,
        ca,
        par,
        max_years=max_years,
        progress=progress,
        tile_cells=tile_cells,
        checkpoint_path=checkpoint_path,
        resume=resume,
        checkpoint_every=checkpoint_every,
    )
    avgpar = np.mean(ipar_wm2, axis=0)
    bpot, ratio, d2wm, ud2w = classify(
        p0,
        lsmk,
        env["tmin"],
        env["meanpp"],
        env["seanpp"],
        avgpar,
        env["wsoil2"],
        uwind,
        fire=fire,
    )
    env.update(
        {
            "bpot": bpot,
            "ratioNPP": ratio,
            "d2wm": d2wm,
            "ud2w": ud2w,
            "avgpar": avgpar,
        }
    )
    return env
