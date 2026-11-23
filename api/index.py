"""
Vercel Serverless Function entry point for AutoHeal DevOps FastAPI backend.
Used when the Vercel project is configured with Root Directory = . (repository root).
"""
import os
import sys

# Ensure the backend directory is on the Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

# Vercel's Python runtime discovers 'app' as the ASGI application
__all__ = ["app"]
