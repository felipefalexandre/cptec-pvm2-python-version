"""Kappa statistic and accuracy metrics, following skill4.f."""

from __future__ import annotations

import numpy as np

NMAX = 12


def remap_legacy_classes(values):
    """skill4.f: seasonal forest 13 -> 12, ice 20 -> 13."""
    out = np.array(values, copy=True)
    out[out.astype(np.int32) == 13] = 12
    out[out.astype(np.int32) == 20] = 13
    return out


def kappa(observed, modelled, nmax=NMAX):
    obs = remap_legacy_classes(np.asarray(observed)).astype(np.int32)
    mod = remap_legacy_classes(np.asarray(modelled)).astype(np.int32)

    nfreq = np.zeros((nmax + 1, nmax + 1), dtype=np.int64)
    for n in range(1, nmax + 1):
        for k in range(1, nmax + 1):
            nfreq[n, k] = np.sum((obs == n) & (mod == k))

    ns_obs = nfreq.sum(axis=1)
    ns_mod = nfreq.sum(axis=0)
    nsum = ns_obs[1:].sum()
    if nsum == 0:
        raise ValueError("no observed cells in classes 1..12")

    p_obs = ns_obs / float(nsum)
    p_mod = ns_mod / float(nsum)

    per_class = {}
    p0 = 0.0
    pe = 0.0
    for n in range(1, nmax + 1):
        po = nfreq[n, n] / float(nsum)
        pe_n = p_obs[n] * p_mod[n]
        p0 += po
        pe += pe_n
        denominator = ((p_obs[n] + p_mod[n]) / 2.0) - pe_n
        kappa_n = (po - pe_n) / denominator if denominator != 0 else np.nan
        total_obs = ns_obs[n]
        accuracy = 100.0 * nfreq[n, n] / total_obs if total_obs else np.nan
        per_class[n] = {
            "observed": int(total_obs),
            "modelled": int(ns_mod[n]),
            "correct": int(nfreq[n, n]),
            "accuracy_percent": float(accuracy),
            "kappa": float(kappa_n),
        }

    overall = (p0 - pe) / (1.0 - pe) if pe != 1.0 else np.nan
    agreement = 100.0 * np.sum(obs == mod) / obs.size
    return {
        "n_compared": int(nsum),
        "grid_cells": int(obs.size),
        "agreement_percent": float(agreement),
        "p0": float(p0),
        "p_e": float(pe),
        "kappa": float(overall),
        "per_class": per_class,
        "confusion_matrix": nfreq[1:, 1:].tolist(),
    }
