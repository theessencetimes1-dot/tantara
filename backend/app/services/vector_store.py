"""Persistent FAISS inner-product index; vectors are normalized at write time."""

import json
import threading

import numpy as np

from app.config import get_settings

# Serializes DB chunk mutations with FAISS updates/reconciliation.
INDEX_LOCK = threading.RLock()


class FaissStore:
    def __init__(self):
        import faiss

        self.faiss = faiss
        self.root = get_settings().data_dir / "index"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "chunks.faiss"
        self.map_path = self.root / "chunk_ids.json"
        self.lock = threading.RLock()
        self.index = None
        self.ids = []
        self._load()

    def _load(self):
        if self.index_path.exists() and self.map_path.exists():
            self.index = self.faiss.read_index(str(self.index_path))
            self.ids = json.loads(self.map_path.read_text())
        else:
            self.index = self.faiss.IndexFlatIP(get_settings().embedding_dimensions)
            self.ids = []

    def _save(self):
        self.faiss.write_index(self.index, str(self.index_path))
        tmp = self.map_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.ids))
        tmp.replace(self.map_path)

    def rebuild(self, rows):
        with self.lock:
            self.index = self.faiss.IndexFlatIP(get_settings().embedding_dimensions)
            self.ids = []
            if rows:
                vec = np.asarray([r[1] for r in rows], dtype="float32")
                self.faiss.normalize_L2(vec)
                self.index.add(vec)
                self.ids = [r[0] for r in rows]
            self._save()

    def add(self, rows):
        with self.lock:
            if not rows:
                return
            vec = np.asarray([r[1] for r in rows], dtype="float32")
            self.faiss.normalize_L2(vec)
            self.index.add(vec)
            self.ids.extend(r[0] for r in rows)
            self._save()

    def remove(self, chunk_ids):
        remove = set(chunk_ids)
        with self.lock:
            if not remove:
                return
            keep = [cid for cid in self.ids if cid not in remove]
            if len(keep) != len(self.ids):
                rows = self._load_vectors()
                self.rebuild([(cid, rows[cid]) for cid in keep if cid in rows])

    def _load_vectors(self):
        return {cid: self.index.reconstruct(i).copy() for i, cid in enumerate(self.ids)}

    def search(self, vector, k=30):
        with self.lock:
            if not self.ids:
                return []
            v = np.asarray([vector], dtype="float32")
            self.faiss.normalize_L2(v)
            scores, idx = self.index.search(v, min(k, len(self.ids)))
            return [(self.ids[i], float(score)) for score, i in zip(scores[0], idx[0], strict=True) if i >= 0]

    def count(self):
        with self.lock:
            return len(self.ids)

    def id_set(self):
        with self.lock:
            return set(self.ids)


def store():
    global _store
    try:
        return _store
    except NameError:
        _store = FaissStore()
        return _store
