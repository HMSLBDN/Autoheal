"""
Vercel ASGI entry point for AutoHeal FastAPI backend.
Discovers and exports the FastAPI instance 'app'.
"""
import os
import sys

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

__all__ = ["app"]
