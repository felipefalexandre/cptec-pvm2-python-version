import json
from pathlib import Path

import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fortran_scalars():
    return json.loads((FIXTURES / "fortran_scalars.json").read_text(encoding="utf8"))


@pytest.fixture(scope="session")
def fortran_bpot_ca350():
    return np.load(FIXTURES / "fortran_bpot_ca350.npy")
