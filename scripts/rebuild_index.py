#!/usr/bin/env python3
"""Rebuild backend/data/index/chunks.faiss from chunk embedding BLOBs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import init_db
from app.services.index_maintenance import rebuild_index

init_db()
print(rebuild_index())
