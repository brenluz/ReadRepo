from functools import lru_cache

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    # Loading the weights is expensive, so do it once and reuse.
    model = SentenceTransformer(settings.embedding_model)
    # Truncate embedding inputs to bound CPU cost; the full chunk text is
    # still what gets stored and handed to the LLM.
    model.max_seq_length = settings.embedding_max_seq_tokens
    return model


class CodeEmbeddings(Embeddings):
    """
    LangChain Embeddings backed by a local sentence-transformers model.
    The model expects task-specific prefixes - documents and queries are
    embedded differently - which maps cleanly onto the two interface
    methods.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [settings.embedding_document_prefix + t for t in texts]
        vectors = _model().encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        prefixed = settings.embedding_query_prefix + text
        vector = _model().encode(prefixed, normalize_embeddings=True)
        return vector.tolist()
