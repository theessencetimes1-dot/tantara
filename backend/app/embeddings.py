"""Typed embedding providers. Semantic search never substitutes fake vectors."""

from typing import Protocol

from app.config import get_settings


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    def __init__(self):
        self._model = None

    def _get(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=get_settings().fastembed_model)
        return self._model

    def embed_documents(self, texts):
        return [v.tolist() for v in self._get().embed(texts)] if texts else []

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class VoyageProvider:
    def _client(self):
        from voyageai import Client

        s = get_settings()
        if not s.enable_cloud_providers or not s.voyage_api_key:
            raise RuntimeError("Voyage is disabled")
        return Client(api_key=s.voyage_api_key)

    def embed_documents(self, texts):
        return [
            list(v)
            for v in self._client()
            .embed(texts, model=get_settings().voyage_embedding_model, input_type="document")
            .embeddings
        ]

    def embed_query(self, text):
        return list(
            self._client()
            .embed([text], model=get_settings().voyage_embedding_model, input_type="query")
            .embeddings[0]
        )


_provider = None


def provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        _provider = FastEmbedProvider() if s.embedding_provider == "fastembed" else VoyageProvider()
    return _provider


def embed_documents(texts):
    return provider().embed_documents(texts)


def embed_query(text):
    return provider().embed_query(text)
