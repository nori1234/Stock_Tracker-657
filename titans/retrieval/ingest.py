from pathlib import Path

from .base import RetrievedChunk

SUPPORTED_SUFFIXES = {".txt", ".md"}


def chunk_text(text: str, max_chars: int = 600, overlap: int = 100) -> list[str]:
    """段落境界を優先しつつ max_chars 以内に分割する。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}" if buf else p
            continue
        if buf:
            chunks.append(buf)
        while len(p) > max_chars:
            chunks.append(p[:max_chars])
            p = p[max_chars - overlap:]
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


def load_directory(directory: str) -> list[RetrievedChunk]:
    """knowledge ディレクトリ配下の .txt/.md を読み込みチャンク化する。"""
    chunks: list[RetrievedChunk] = []
    root = Path(directory)
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for c in chunk_text(text):
            chunks.append(RetrievedChunk(text=c, source=str(path.relative_to(root))))
    return chunks
