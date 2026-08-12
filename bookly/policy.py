"""
Policy retrieval.

Keyword and token overlap over a small curated corpus. No vector database, and
that is a decision rather than a shortcut. See the note at the bottom.

What matters is not retrieval quality. Every passage carries a stable id and the
agent must return it when making a policy claim. That turns "do not make things
up" from a request into something a reviewer can check afterwards.
"""

import re
from .data import POLICY_PASSAGES

_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "did", "i", "my", "me", "you",
    "your", "it", "to", "of", "for", "and", "or", "if", "in", "on", "can", "how",
    "what", "when", "where", "will", "would", "should", "be", "been", "have",
    "has", "get", "got", "want", "need", "please", "hi", "hello", "thanks",
}


def _tokenise(text: str):
    tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _score(query: str, passage: dict) -> float:
    """
    Weighted keyword hits plus token overlap with the passage body.

    Keywords score higher because they are hand-curated intent signals. Same
    reason a real deployment curates its help centre rather than trusting raw
    embeddings over whatever content happens to exist.
    """
    q_lower = (query or "").lower()
    q_tokens = set(_tokenise(query))

    keyword_score = 0.0
    for kw in passage["keywords"]:
        if kw in q_lower:
            keyword_score += 3.0
        else:
            kw_tokens = set(_tokenise(kw))
            if kw_tokens and kw_tokens.issubset(q_tokens):
                keyword_score += 2.0

    body_tokens = set(_tokenise(passage["title"] + " " + passage["text"]))
    overlap = len(q_tokens & body_tokens)

    return keyword_score + (overlap * 0.5)


# Below this score, return nothing rather than the least-bad match. The most
# consequential number in this file. It is the difference between an agent that
# says "I don't know" and one that improvises.
MIN_RELEVANCE = 2.0


def search_policy(query: str, top_k: int = 3):
    """
    Return the most relevant passages, or an empty list.

    Empty is a useful result. The agent is instructed to hand off rather than
    answer when retrieval finds nothing.
    """
    scored = [(_score(query, p), p) for p in POLICY_PASSAGES]
    hits = [(s, p) for s, p in scored if s >= MIN_RELEVANCE]
    hits.sort(key=lambda pair: pair[0], reverse=True)

    return [
        {
            "passage_id": p["id"],
            "title": p["title"],
            "text": p["text"],
            "relevance": round(s, 2),
        }
        for s, p in hits[:top_k]
    ]


# Why keyword retrieval and not embeddings
#
# For nine passages, embeddings add an API dependency, latency, and a similarity
# threshold that is harder to reason about, in exchange for better paraphrase
# handling. At a real help centre's scale, a few hundred articles, I would use
# hybrid retrieval: BM25 for exact policy terms plus embeddings for paraphrase,
# with reciprocal rank fusion.
#
# The citation contract and the threshold rule would not change. Those are
# architectural. The retriever is an implementation detail.
