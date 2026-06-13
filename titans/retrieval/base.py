import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float = 0.0


class Retriever(ABC):
    """Retrieval Layer の共通契約 (Qdrant / BM25 / 将来の GraphRAG)。"""

    @abstractmethod
    def add(self, chunks: list[RetrievedChunk]) -> None:
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


_ASCII_WORD = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ]")


def tokenize(text: str) -> list[str]:
    """
    依存ゼロの日英対応トークナイザ。
    英数字は単語単位、日本語(CJK)は文字ユニグラム+バイグラム。
    形態素解析器(Sudachi等)への差し替えはこの関数の置換のみで可能。
    """
    text = text.lower()
    tokens = _ASCII_WORD.findall(text)
    chars = _CJK.findall(text)
    tokens.extend(chars)
    tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens
