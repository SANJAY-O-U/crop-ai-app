"""
Makes `research/` (for `pipeline...`, `era5_land...`, `config`) and
`backend/` (for `app...`, needed by pipeline/baseline_eval.py's import of
the production lapse-rate constant) importable during pytest collection,
matching the same no-__init__.py namespace-package convention already used
by backend/conftest.py.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
