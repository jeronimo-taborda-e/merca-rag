"""Modelos de embeddings: multilingual-e5-small (384) y CLIP ViT-B/32 (512).

Todas las funciones reciben LISTAS (procesar en lote es más rápido) y devuelven
vectores de norma 1, así coseno, producto interno y L2 ordenan igual.

e5 necesita prefijos: "passage: " para lo que se guarda y "query: " para lo que se pregunta.
  * embed_consulta(preguntas)  -> añade "query: "
  * embed_oraciones(oraciones) -> añade "query: " (comparación oración-oración del chunking semántico)
  * embed_pasajes(textos)      -> recibe el texto YA armado con texto_para_vectorizar ("passage: ...")
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import config


class Modelos:
    """Carga perezosa: cada modelo se descarga/carga la primera vez que se usa.

    Los modelos quedan en el volumen de Docker modelos_hf (se descargan una sola vez).
    """

    def __init__(self, dispositivo: str = "cpu"):
        self.dispositivo = dispositivo
        self._texto = None
        self._clip_imagen = None
        self._clip_texto = None
        # Caché texto -> vector: el mismo texto (ya con su prefijo) se vectoriza una sola vez.
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
    def tokenizador(self):
        """Tokenizador del modelo de texto: con él se miden TODOS los tamaños de chunk."""
        return self.texto.tokenizer

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
            cache.update(zip(faltan, np.asarray(vectores, dtype=np.float32)))
        return np.vstack([cache[t] for t in textos])

    def _embed_e5(self, textos: list[str], batch_size: int = 32) -> np.ndarray:
        return self._con_cache(self._cache_texto, self.texto, textos, config.DIM_TEXTO, batch_size)

    def embed_consulta(self, preguntas: list[str], batch_size: int = 32) -> np.ndarray:
        """Preguntas del usuario (prefijo "query: ")."""
        return self._embed_e5([config.PREFIJO_CONSULTA + p for p in preguntas], batch_size)

    def embed_oraciones(self, oraciones: list[str], batch_size: int = 32) -> np.ndarray:
        """Oraciones para comparar entre sí en el chunking semántico (prefijo "query: ", tarea simétrica)."""
        return self._embed_e5([config.PREFIJO_CONSULTA + o for o in oraciones], batch_size)

    def embed_pasajes(self, textos_completos: list[str], batch_size: int = 32) -> np.ndarray:
        """Chunks ya armados con texto_para_vectorizar (incluyen "passage: " y el título)."""
        return self._embed_e5(textos_completos, batch_size)

    def embed_texto_clip(self, textos: list[str], batch_size: int = 32) -> np.ndarray:
        """Texto en el espacio CLIP (512), con el codificador de texto multilingüe."""
        return self._con_cache(self._cache_clip, self.clip_texto, textos, config.DIM_CLIP, batch_size)

    def limpiar_cache(self) -> None:
        self._cache_texto.clear()
        self._cache_clip.clear()

    def embed_imagenes(self, imagenes: list[Image.Image], batch_size: int = 16) -> np.ndarray:
        """Vectoriza los PÍXELES (no la ruta del archivo)."""
        return np.asarray(self.clip_imagen.encode(list(imagenes), batch_size=batch_size, normalize_embeddings=True,
                                                  convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)

    # -------------------------------------------------------------- tokens
    def contar_tokens(self, texto: str) -> int:
        """Tokens del tokenizador de e5, con los especiales y sin truncar."""
        # verbose=False: no mostrar el aviso "sequence length is longer than..."; aquí
        # justamente se quiere saber cuántos tokens tiene el texto aunque pase del límite
        return len(self.tokenizador(texto, add_special_tokens=True, truncation=False,
                                    verbose=False)["input_ids"])


def abrir_imagen(ruta: str | Path) -> Image.Image:
    """Abre una foto corrigiendo la orientación EXIF (fotos de celular) y en RGB."""
    with Image.open(ruta) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def texto_sin_prefijo(titulo: str, chunk: str) -> str:
    """Título + chunk (si ANTEPONER_TITULO). Es lo que se vectoriza en el espacio CLIP."""
    return f"{titulo}. {chunk}" if config.ANTEPONER_TITULO and titulo else chunk


def texto_para_vectorizar(titulo: str, chunk: str) -> str:
    """Lo que realmente lee e5: "passage: " + título + chunk. Con esto se cuentan los n_tokens."""
    return config.PREFIJO_PASAJE + texto_sin_prefijo(titulo, chunk)
