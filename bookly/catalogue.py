"""
Catalogue and reading community data.

Supports the second half of the thesis: authority tiered by recoverability.
Refunds cannot be undone, so they are gated. Recommendations can, so the agent
gets to be generous.

Two things about the data.

Recommendations are grounded here and must return a book_id. The model cannot
invent a title for the same reason it cannot invent a policy. A customer ordering
a book that does not exist is a ticket the agent created.

Book clubs are real objects with schedules and sizes, not a vague nudge to join
the community. A concierge makes a specific offer.
"""

from datetime import date, timedelta

TODAY = date.today()


def _in_days(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# Catalogue, weighted towards fantasy and literary fiction because that is where
# Bookly's community is. The `mood` and `themes` fields make recommendation
# something other than genre matching. "Something like Piranesi" is a request
# about atmosphere, not shelf category.
#
# `shop_cat_pick` is the staff-picks shelf, curated by Tiberius the bookshop cat.
# A brand detail rather than a feature, but it gives the agent something warm and
# specific to reach for.

CATALOGUE = {
    "BK-0001": {
        "book_id": "BK-0001",
        "title": "The Fifth Season",
        "author": "N. K. Jemisin",
        "genre": "fantasy",
        "price": 9.99,
        "themes": ["apocalyptic", "systemic injustice", "geology", "motherhood"],
        "mood": ["angry", "propulsive", "bleak"],
        "pace": "fast",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "A world that ends regularly, and the people the world blames for it.",
    },
    "BK-0002": {
        "book_id": "BK-0002",
        "title": "Piranesi",
        "author": "Susanna Clarke",
        "genre": "fantasy",
        "price": 14.99,
        "themes": ["labyrinth", "memory", "solitude", "wonder"],
        "mood": ["dreamlike", "gentle", "eerie"],
        "pace": "slow",
        "in_stock": True,
        "shop_cat_pick": True,
        "blurb": "A house of endless halls and tides, and the man who keeps its records.",
    },
    "BK-0003": {
        "book_id": "BK-0003",
        "title": "Babel",
        "author": "R. F. Kuang",
        "genre": "fantasy",
        "price": 18.50,
        "themes": ["colonialism", "language", "academia", "betrayal"],
        "mood": ["angry", "cerebral", "tragic"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "Translation as magic, and empire as the thing magic is for.",
    },
    "BK-0004": {
        "book_id": "BK-0004",
        "title": "Jonathan Strange & Mr Norrell",
        "author": "Susanna Clarke",
        "genre": "fantasy",
        "price": 12.99,
        "themes": ["english magic", "rivalry", "faerie", "footnotes"],
        "mood": ["dreamlike", "witty", "eerie"],
        "pace": "slow",
        "in_stock": True,
        "shop_cat_pick": True,
        "blurb": "The return of magic to England, told as if by a very dry historian.",
    },
    "BK-0005": {
        "book_id": "BK-0005",
        "title": "The Buried Giant",
        "author": "Kazuo Ishiguro",
        "genre": "literary fiction",
        "price": 10.99,
        "themes": ["memory", "marriage", "myth", "forgetting"],
        "mood": ["dreamlike", "melancholy", "gentle"],
        "pace": "slow",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "An elderly couple cross a mist-covered Britain looking for a son they can barely recall.",
    },
    "BK-0006": {
        "book_id": "BK-0006",
        "title": "Sea of Tranquility",
        "author": "Emily St. John Mandel",
        "genre": "literary fiction",
        "price": 16.00,
        "themes": ["time travel", "pandemic", "art", "simulation"],
        "mood": ["melancholy", "hopeful", "cerebral"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "Four centuries, one anomaly in a forest, and the question of what is real.",
    },
    "BK-0007": {
        "book_id": "BK-0007",
        "title": "Klara and the Sun",
        "author": "Kazuo Ishiguro",
        "genre": "literary fiction",
        "price": 15.00,
        "themes": ["artificial intelligence", "devotion", "illness", "observation"],
        "mood": ["melancholy", "gentle", "unsettling"],
        "pace": "slow",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "An artificial friend watches a family very carefully, and understands most of it.",
    },
    "BK-0008": {
        "book_id": "BK-0008",
        "title": "Tomorrow, and Tomorrow, and Tomorrow",
        "author": "Gabrielle Zevin",
        "genre": "literary fiction",
        "price": 22.00,
        "themes": ["friendship", "game design", "creative partnership", "disability"],
        "mood": ["warm", "propulsive", "melancholy"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "Two friends make video games for thirty years and never quite say the thing.",
    },
    "BK-0009": {
        "book_id": "BK-0009",
        "title": "The Master and Margarita",
        "author": "Mikhail Bulgakov",
        "genre": "literary fiction",
        "price": 11.50,
        "themes": ["devil", "satire", "moscow", "cats"],
        "mood": ["chaotic", "witty", "eerie"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": True,
        "blurb": "The devil visits Soviet Moscow with a retinue including an enormous talking cat.",
    },
    "BK-0010": {
        "book_id": "BK-0010",
        "title": "The Travelling Cat Chronicles",
        "author": "Hiro Arikawa",
        "genre": "literary fiction",
        "price": 8.99,
        "themes": ["cats", "friendship", "road trip", "mortality"],
        "mood": ["warm", "melancholy", "gentle"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": True,
        "blurb": "A cat narrates a journey across Japan and is extremely clear about who is in charge.",
    },
    "BK-0011": {
        "book_id": "BK-0011",
        "title": "A Wizard of Earthsea",
        "author": "Ursula K. Le Guin",
        "genre": "fantasy",
        "price": 8.99,
        "themes": ["true names", "pride", "shadow", "apprenticeship"],
        "mood": ["spare", "mythic", "gentle"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": True,
        "blurb": "A boy learns magic, overreaches, and spends the book putting it right.",
    },
    "BK-0012": {
        "book_id": "BK-0012",
        "title": "The Goblin Emperor",
        "author": "Katherine Addison",
        "genre": "fantasy",
        "price": 10.50,
        "themes": ["court politics", "kindness", "outsider", "grief"],
        "mood": ["warm", "anxious", "hopeful"],
        "pace": "medium",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "A despised fourth son inherits a throne and decides to be decent about it.",
    },
    "BK-0013": {
        "book_id": "BK-0013",
        "title": "Piranesi's Halls: A Reader's Companion",
        "author": "Various",
        "genre": "nonfiction",
        "price": 6.99,
        "themes": ["labyrinth", "criticism", "wonder"],
        "mood": ["cerebral"],
        "pace": "slow",
        "in_stock": False,
        "shop_cat_pick": False,
        "blurb": "Essays on Clarke's second novel. Currently out of print.",
    },
    "BK-0014": {
        "book_id": "BK-0014",
        "title": "The Song of Achilles",
        "author": "Madeline Miller",
        "genre": "fantasy",
        "price": 9.50,
        "themes": ["myth retelling", "love", "fate", "grief"],
        "mood": ["tragic", "warm", "propulsive"],
        "pace": "fast",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "The Iliad, from the point of view of the person with the most to lose.",
    },
    "BK-0015": {
        "book_id": "BK-0015",
        "title": "Gideon the Ninth",
        "author": "Tamsyn Muir",
        "genre": "fantasy",
        "price": 11.99,
        "themes": ["necromancy", "locked room", "loyalty", "swords"],
        "mood": ["chaotic", "witty", "propulsive"],
        "pace": "fast",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "Necromancers in space, a haunted house, and a great deal of attitude.",
    },
}


# Book clubs, with a date, a size and a format. "Why not join our community" is
# not an offer. "Eleven people are discussing this on the 24th" is.

BOOK_CLUBS = {
    "CLB-001": {
        "club_id": "CLB-001",
        "name": "The Hall of Statues",
        "focus": "fantasy",
        "themes": ["labyrinth", "memory", "wonder", "english magic", "faerie"],
        "current_book_id": "BK-0002",
        "next_meeting": _in_days(12),
        "members": 340,
        "format": "online, Thursday evenings",
        "description": "Slow, strange, atmospheric fantasy. Currently three chapters behind schedule and unbothered.",
    },
    "CLB-002": {
        "club_id": "CLB-002",
        "name": "Burn It Down",
        "focus": "fantasy",
        "themes": ["colonialism", "systemic injustice", "apocalyptic", "empire"],
        "current_book_id": "BK-0003",
        "next_meeting": _in_days(5),
        "members": 512,
        "format": "online, Sunday afternoons",
        "description": "Fantasy that has an argument to make. Expect the argument.",
    },
    "CLB-003": {
        "club_id": "CLB-003",
        "name": "Tiberius's Shelf",
        "focus": "cats",
        "themes": ["cats", "friendship", "mortality", "wonder"],
        "current_book_id": "BK-0010",
        "next_meeting": _in_days(3),
        "members": 128,
        "format": "online, Tuesday lunchtimes",
        "description": "Books with cats in them, chosen by the shop cat. He has never been wrong and never explains.",
    },
    "CLB-004": {
        "club_id": "CLB-004",
        "name": "The Long Now",
        "focus": "literary fiction",
        "themes": ["memory", "time travel", "mortality", "artificial intelligence"],
        "current_book_id": "BK-0006",
        "next_meeting": _in_days(9),
        "members": 274,
        "format": "online, Monday evenings",
        "description": "Literary fiction about time, memory and what survives. Quiet, thoughtful, occasionally devastating.",
    },
    "CLB-005": {
        "club_id": "CLB-005",
        "name": "First Time Round",
        "focus": "fantasy",
        "themes": ["apprenticeship", "myth retelling", "court politics", "true names"],
        "current_book_id": "BK-0011",
        "next_meeting": _in_days(7),
        "members": 89,
        "format": "online, Saturday mornings",
        "description": "For people new to fantasy, or coming back to it. No prior reading assumed, no gatekeeping tolerated.",
    },
}


# Similarity, deliberately not a model call. Weighted overlap on themes and mood,
# with genre as a weak signal rather than a filter, so "something like Piranesi"
# can return literary fiction.
#
# Arithmetic because it is cheap, instant, inspectable and identical every time.
# A customer asking twice gets the same answer, and I can explain why any book was
# suggested. None of that holds if you ask a model to free-associate.

_MOOD_WEIGHT = 2.0
_THEME_WEIGHT = 3.0
_GENRE_WEIGHT = 1.0
_PACE_WEIGHT = 0.5


def similarity(a: dict, b: dict) -> float:
    score = 0.0
    score += _THEME_WEIGHT * len(set(a["themes"]) & set(b["themes"]))
    score += _MOOD_WEIGHT * len(set(a["mood"]) & set(b["mood"]))
    if a["genre"] == b["genre"]:
        score += _GENRE_WEIGHT
    if a["pace"] == b["pace"]:
        score += _PACE_WEIGHT
    return score


def find_by_title(title: str):
    """Loose title match. Returns the book or None, never a best guess."""
    needle = (title or "").strip().lower()
    if not needle:
        return None
    for book in CATALOGUE.values():
        if book["title"].lower() == needle:
            return book
    # Substring fallback, only when it matches exactly one book. Ambiguity
    # returns None so the agent asks rather than chooses.
    partial = [b for b in CATALOGUE.values() if needle in b["title"].lower()]
    return partial[0] if len(partial) == 1 else None


def similar_to(book: dict, limit: int = 3, exclude_ids=None):
    exclude = set(exclude_ids or []) | {book["book_id"]}
    scored = [
        (similarity(book, other), other)
        for other in CATALOGUE.values()
        if other["book_id"] not in exclude and other["in_stock"]
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["title"]))
    return [(s, b) for s, b in scored[:limit] if s > 0]


def clubs_for_book(book: dict, limit: int = 2):
    """Clubs whose themes overlap the book's, most relevant first."""
    scored = []
    for club in BOOK_CLUBS.values():
        overlap = len(set(club["themes"]) & set(book["themes"]))
        if club["current_book_id"] == book["book_id"]:
            overlap += 5  # actively reading it beats thematic adjacency
        if overlap > 0:
            scored.append((overlap, club))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    return [c for _, c in scored[:limit]]


def shop_cat_picks():
    return [b for b in CATALOGUE.values() if b["shop_cat_pick"] and b["in_stock"]]
