"""
Searching the shop's written policies.

The AI knows a lot about bookshops in general. Ask it about returns and it can
produce a confident, well-written answer that has nothing to do with OUR rules.
Fourteen days, twenty-eight, sixty; all of those are real policies somewhere.

So it is only allowed to quote policy we hand it. This file finds the right
passage and sends it over with a reference number like POL-RET-01. The AI must
put that reference in its reply, which means anyone reading the conversation
afterwards can check the answer against the actual document.

The search itself is plain arithmetic: count matching words, add up a score.
No AI involved. See the note at the bottom for why.
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


def _score(query: str, passage: dict) -> tuple:
    """
    Score one passage against the question. Returns (keyword, overlap_ratio).

    Two parts, kept separate on purpose.

    Keyword hits are the signal that matters. Three points if the phrase appears
    in the question as written, two if all its words turn up scattered about.
    Someone chose these deliberately.

    Word overlap is normalised by the number of content words in the question, so
    it reports the FRACTION of the question a passage covers rather than a raw
    count. The unnormalised version summed matches, so a rambling question
    accumulated overlap against every passage and dragged an irrelevant one over
    the cutoff. A 65 word question about loyalty points scored 3.5 against the gift
    card passage, while the six word version correctly scored nothing.
    """
    q_lower = (query or "").lower()
    q_tokens = set(_tokenise(query))

    keyword_score = 0.0
    for kw in passage["keywords"]:
        if kw in q_lower:
            keyword_score += 3.0
        else:
            kw_tokens = set(_tokenise(kw))
            # Two content words minimum for the scattered match. A long keyword
            # like "when will i get my money" reduces to {"money"} once stopwords
            # go, and then any question mentioning money matched it. A single
            # content word has to appear as a phrase, which is the branch above.
            if len(kw_tokens) >= 2 and kw_tokens.issubset(q_tokens):
                keyword_score += 2.0

    body_tokens = set(_tokenise(passage["title"] + " " + passage["text"]))
    overlap = len(q_tokens & body_tokens)
    ratio = overlap / len(q_tokens) if q_tokens else 0.0

    return keyword_score, ratio


# Two thresholds, because the two signals mean different things.
#
# A passage qualifies on a hand-picked keyword hit, or on covering a real fraction
# of the question. Below both, return NOTHING rather than whatever scored highest.
#
# Without a cutoff there is always a least-bad match. Someone asks about loyalty
# points, nothing really fits, and we hand over the gift card passage. Now the AI
# has a document about gift cards, a question about loyalty points, and
# instructions to answer from the document. It will produce something. It will read
# well. It will be wrong.
#
# "I do not know" only happens if you build for it.
MIN_KEYWORD_SCORE = 2.0
MIN_OVERLAP_RATIO = 0.34


def search_policy(query: str, top_k: int = 3):
    """
    Return the best matching passages, or an empty list if nothing fits.

    An empty list is a real answer, not a failure. When it happens the agent is
    told to say it does not know and offer a human.
    """
    scored = [(_score(query, p), p) for p in POLICY_PASSAGES]
    hits = [
        (kw, ratio, p) for (kw, ratio), p in scored
        if kw >= MIN_KEYWORD_SCORE or ratio >= MIN_OVERLAP_RATIO
    ]
    hits.sort(key=lambda t: (t[0], t[1]), reverse=True)

    return [
        {
            "passage_id": p["id"],
            "title": p["title"],
            "text": p["text"],
            "keyword_score": round(kw, 2),
            "overlap_ratio": round(ratio, 2),
        }
        for kw, ratio, p in hits[:top_k]
    ]


# Why counting words instead of "proper" search
#
# The usual approach is embeddings: turn each passage into a long list of
# numbers that captures its meaning, do the same to the question, and find the
# closest. It handles rephrasing better. "How do I send this back" and "returns
# policy" share no words but mean the same thing.
#
# For nine passages that is not worth it. It means an extra API call before
# every search, more waiting for the customer, and a similarity cutoff with no
# obvious right value. Instead the rephrasing cases are handled by hand: note
# that "send back" is in the keyword list below.
#
# A vector database would be further overkill still. Those exist to search
# millions of vectors quickly, using a method that is deliberately approximate.
# Nine vectors is nine sums. There is nothing to speed up.
#
# At a few hundred help articles I would use both: word matching for exact
# policy terms, embeddings for rephrasing, results merged.
#
# What would NOT change is the reference number rule and the cutoff above.
# Those are the design. The search underneath is swappable.
