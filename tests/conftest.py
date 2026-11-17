"""Gemeinsame Fixtures: die Mini-Instanz, an der jede Einheit von Hand geprüft wird (DEMO-PLAYBOOK §1b)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def mini():
    """Zwei Stunden in Viertelstunden: 10 kW, 4 × 10 kW, 2 × 70 kW, 2 × 10 kW (Last − PV). Handrechnung siehe tests/test_algorithm.py."""
    return np.array([10.0, 10.0, 10.0, 10.0, 70.0, 70.0, 10.0, 10.0])
