"""
Ensures `backend/` (this file's directory) is on sys.path so `import app...`
resolves the same way it does when running `python -m uvicorn app.main:app`
from this directory — the existing app/ package has no __init__.py files, so
without this, pytest run from elsewhere can't find it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
