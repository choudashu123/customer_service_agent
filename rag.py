"""
Lightweight in-memory RAG over the markdown policy corpus in policy_docs/.

No external services or model downloads: documents are split into section-level
chunks and ranked with Okapi BM25 (pure Python). This is the retrieval half of
the pipeline; the agent calls search() through the `search_policy` tool and
writes the grounded answer.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent / "policy_docs"

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "to", "is", "are", "and", "or", "in", "on", "for",
    "it", "be", "as", "at", "by", "if", "that", "this", "with", "from", "will",
    "can", "i", "my", "you", "your", "we", "our", "they", "their", "not", "no",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 1]


class _Chunk:
    __slots__ = ("source", "heading", "text", "tokens", "tf")

    def __init__(self, source: str, heading: str, text: str) -> None:
        self.source = source
        self.heading = heading
        self.text = text
        self.tokens = _tokenize(heading + " " + heading + " " + text)  # weight heading
        self.tf: dict[str, int] = {}
        for t in self.tokens:
            self.tf[t] = self.tf.get(t, 0) + 1


class PolicyIndex:
    """Okapi BM25 over section chunks. Rebuilt cheaply on process start."""

    K1 = 1.5
    B = 0.75

    def __init__(self, docs_dir: Path = DOCS_DIR) -> None:
        self.chunks: list[_Chunk] = []
        self._df: dict[str, int] = {}
        self._avg_len = 0.0
        self._load(docs_dir)

    def _load(self, docs_dir: Path) -> None:
        for path in sorted(docs_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            doc_title = path.stem.replace("-", " ").title()
            parts = re.split(r"^##\s+", raw, flags=re.M)
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                if i == 0:
                    heading = doc_title
                    body = re.sub(r"^#\s+.*$", "", part, flags=re.M).strip()
                else:
                    line, _, rest = part.partition("\n")
                    heading = f"{doc_title} — {line.strip()}"
                    body = rest.strip()
                if body:
                    self.chunks.append(_Chunk(path.name, heading, body))

        for c in self.chunks:
            for term in set(c.tokens):
                self._df[term] = self._df.get(term, 0) + 1
        if self.chunks:
            self._avg_len = sum(len(c.tokens) for c in self.chunks) / len(self.chunks)

    def _idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 3) -> list[dict]:
        """Okapi BM25 search over the section chunks."""
        q_terms = _tokenize(query)
        if not q_terms or not self.chunks:
            return []
        scored: list[tuple[float, _Chunk]] = []
        for c in self.chunks:
            dl = len(c.tokens) or 1
            score = 0.0
            for term in q_terms:
                if term not in c.tf:
                    continue
                freq = c.tf[term]
                num = freq * (self.K1 + 1)
                den = freq + self.K1 * (1 - self.B + self.B * dl / (self._avg_len or 1))
                score += self._idf(term) * num / den
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"source": c.source, "heading": c.heading, "text": c.text,
             "score": round(s, 3)}
            for s, c in scored[:k]
        ]

_INDEX: PolicyIndex | None = None


def get_index() -> PolicyIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = PolicyIndex()
    return _INDEX


def search(query: str, k: int = 3) -> list[dict]:
    return get_index().search(query, k)
