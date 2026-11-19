"""Modelos de embeddings: MiniLM multilingüe (384) y CLIP ViT-B/32 (512).

Todas las funciones reciben LISTAS (procesar en lote es más rápido) y devuelven
vectores de norma 1, así coseno, producto interno y L2 ordenan igual.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import config


class Modelos:
    """Carga perezosa: cada modelo se descarga/carga la primera vez que se usa.

    Los modelos quedan en el volumen de Docker modelos_hf (~1,6 GB la primera vez).
    """

    def __init__(self, dispositivo: str = "cpu"):
        self.dispositivo = dispositivo
        self._texto = None
        self._clip_imagen = None
        self._clip_texto = None
        # Caché texto -> vector: el mismo texto (una oración, un chunk o una pregunta) se
        # vectoriza una sola vez aunque se pida muchas veces (p. ej. al probar varios umbrales).
        self._cache_texto: dict[str, np.ndarray] = {}
        self._cache_clip: dict[str, np.ndarray] = {}

    # -------------------------------------------------------------- modelos
    @property
    def texto(self):
        if self._texto is None:
            from sentence_transformers import SentenceTransformer
            self._texto = SentenceTransformer(config.MODELO_TEXTO, device=self.dispositivo)
            self._texto.max_seq_length = config.MAX_SEQ_TEXTO
        return self._texto

    @property
    def clip_imagen(self):
        if self._clip_imagen is None:
            from sentence_transformers import SentenceTransformer
            self._clip_imagen = SentenceTransformer(config.MODELO_CLIP_IMAGEN, device=self.dispositivo)
        return self._clip_imagen

    @property
    def clip_texto(self):
        if self._clip_texto is None:
            from sentence_transformers import SentenceTransformer
            self._clip_texto = SentenceTransformer(config.MODELO_CLIP_TEXTO, device=self.dispositivo)
        return self._clip_texto

    def dimensiones(self) -> dict:
        """Se calculan en vez de escribirse a mano (deben coincidir con el esquema)."""
        return {
            "texto": self.texto.get_sentence_embedding_dimension(),
            "clip_texto": self.clip_texto.get_sentence_embedding_dimension(),
            "clip_imagen": int(self.embed_imagenes([Image.new("RGB", (32, 32))]).shape[1]),
        }

    # -------------------------------------------------------------- embeddings
    @staticmethod
    def _con_cache(cache: dict, modelo, textos, dim: int, batch_size: int) -> np.ndarray:
        textos = list(textos)
        if not textos:
            return np.zeros((0, dim), dtype=np.float32)
        faltan = [t for t in dict.fromkeys(textos) if t not in cache]
        if faltan:
            vectores = modelo.encode(faltan, batch_size=batch_size, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=len(faltan) > 500)
            cache.update(zip(faltan, vectores.astype(np.float32)))
        return np.vstack([cache[t] for t in textos])

    def embed_texto(self, textos: list[str], batch_size: int = 32) -> np.ndarray:
        return self._con_cache(self._cache_texto, self.texto, textos, config.DIM_TEXTO, batch_size)

    def embed_texto_clip(self, textos: list[str], batch_size: int = 32) -> np.ndarray:
        return self._con_cache(self._cache_clip, self.clip_texto, textos, config.DIM_CLIP, batch_size)

    def limpiar_cache(self) -> None:
        self._cache_texto.clear()
        self._cache_clip.clear()

    def embed_imagenes(self, imagenes: list[Image.Image], batch_size: int = 16) -> np.ndarray:
        """Vectoriza los PÍXELES (no la ruta del archivo)."""
        return self.clip_imagen.encode(list(imagenes), batch_size=batch_size, normalize_embeddings=True,
                                       convert_to_numpy=True, show_progress_bar=False).astype(np.float32)

    # -------------------------------------------------------------- tokens
    def contar_tokens(self, texto: str) -> int:
        """Tokens del tokenizador de MiniLM, sin truncar (para medir truncamiento)."""
        # verbose=False: no mostrar el aviso "sequence length is longer than..."; aquí
        # justamente se quiere saber cuántos tokens tiene el chunk aunque pase del límite
        return len(self.texto.tokenizer(texto, add_special_tokens=True, truncation=False,
                                        verbose=False)["input_ids"])


def abrir_imagen(ruta: str | Path) -> Image.Image:
    """Abre una foto corrigiendo la orientación EXIF (fotos de celular) y en RGB."""
    with Image.open(ruta) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def texto_para_vectorizar(titulo: str, chunk: str) -> str:
    """Lo que realmente se vectoriza: título + chunk (si ANTEPONER_TITULO)."""
    return f"{titulo}. {chunk}" if config.ANTEPONER_TITULO and titulo else chunk
