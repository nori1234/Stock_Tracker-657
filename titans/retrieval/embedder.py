import hashlib
import math
from abc import ABC, abstractmethod

from .base import tokenize


class Embedder(ABC):
    """ベクトル化の抽象。実装を差し替えても Qdrant 側は変更不要。"""

    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...


class HashingEmbedder(Embedder):
    """
    オフライン動作のデフォルト埋め込み（feature hashing）。
    モデルダウンロード不要・決定論的。語彙の重なりベースの「字句的」類似であり
    意味的類似ではない点に注意 — 本番では OllamaEmbedder 等に差し替える。
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 128) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OllamaEmbedder(Embedder):
    """
    Ollama の埋め込みモデル（例: nomic-embed-text）を使う本番用実装。
    モデルが pull 済みの環境でのみ使用可能。
    初期化時に実際のモデル出力次元を自動検出するため、config の embedding_dim と
    モデルの次元が一致していなくても正しく動作する。
    """

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434", dim: int = 768):
        self._model = model
        self._base_url = base_url
        # モデルに1回問い合わせて実際の次元を取得（config値より優先）
        try:
            import ollama as ollama_client
            client = ollama_client.Client(host=self._base_url)
            test = client.embeddings(model=self._model, prompt="hi")
            self.dim = len(test["embedding"])
        except Exception:
            self.dim = dim  # サーバー未起動時は引数値をフォールバックとして使う

    def embed(self, text: str) -> list[float]:
        import ollama as ollama_client
        client = ollama_client.Client(host=self._base_url)
        res = client.embeddings(model=self._model, prompt=text)
        return list(res["embedding"])


def create_embedder(kind: str, dim: int, base_url: str = "http://localhost:11434") -> Embedder:
    if kind == "hashing":
        return HashingEmbedder(dim=dim)
    if kind == "ollama":
        return OllamaEmbedder(base_url=base_url, dim=dim)
    raise ValueError(f"Unknown embedder: {kind}")
