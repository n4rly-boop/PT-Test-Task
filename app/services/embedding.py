from typing import List, Union

import numpy as np
from sentence_transformers import SentenceTransformer
from app.core.config import settings
import re
import nltk


class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers"""
    
    def __init__(self):
        self.model = None

    def _ensure_model_loaded(self) -> None:
        """Load the sentence transformer model if it has not been loaded yet."""
        if self.model is not None:
            return
        try:
            self.model = SentenceTransformer(settings.embedding_model)
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {e}")
    
    def embed_documents(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Generate embeddings for text(s)
        
        Args:
            texts: Single text string or list of text strings
            
        Returns:
            Embeddings as numpy array(s)
        """
        self._ensure_model_loaded()
        
        try:
            embeddings = self.model.encode(texts)
            return [embedding.tolist() for embedding in embeddings]
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {e}")

# Global embedding service instance (model loads lazily on first use)
embedding_service = EmbeddingService()

def clear_text(text: str) -> str:
    #TODO add lemmatization/stemming for russian words
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t ')
    lowered = text.lower()
    normalized = re.sub(r"[^а-яА-Яa-zA-Z0-9\s]+", " ", lowered)
    removed_spaces = re.sub(r"\s+", " ", normalized)
    stopwords = nltk.corpus.stopwords.words("russian")
    cleared_tokens = [token for token in removed_spaces.split() if token not in stopwords]
    return " ".join(cleared_tokens)