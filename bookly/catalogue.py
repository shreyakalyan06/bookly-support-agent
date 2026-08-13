"""
The books we sell.

This file exists to show the other side of the design. Refunds are locked down
because they cannot be undone. Book suggestions have no checks at all, because a
bad one costs nothing.

Two things to notice.

The AI can only suggest books that are in here and in stock. It knows thousands
of real books and would happily recommend one we have never sold, which creates
a support problem rather than solving one.

Reading groups are real objects with real dates and member counts. "Why not join
our community" is not an offer. "Eleven people are discussing this on the 24th"
is.
"""

from datetime import date

TODAY = date.today()


# The catalogue.
#
# The interesting fields are `themes` and `mood`. Without them, matching books
# means matching genres, and genre is a poor guide. Someone asking for
# "something like Piranesi" is describing an atmosphere, not a shelf. They might
# well want a literary novel rather than more fantasy.
#
# `shop_cat_pick` is the staff picks shelf, chosen by Tiberius the shop cat. A
# bit of shop personality rather than a feature, but it gives the agent
# something specific and warm to reach for.

CATALOGUE = {
    "BK-0001": {
        "book_id": "BK-0001",
        "title": "The Fifth Season",
        "author": "N. K. Jemisin",
        "genre": "fantasy",
        "price_pence": 999,
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
        "price_pence": 1499,
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
        "price_pence": 1850,
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
        "price_pence": 1299,
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
        "price_pence": 1099,
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
        "price_pence": 1600,
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
        "price_pence": 1500,
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
        "price_pence": 2200,
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
        "price_pence": 1150,
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
        "price_pence": 899,
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
        "price_pence": 899,
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
        "price_pence": 1050,
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
        "price_pence": 699,
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
        "price_pence": 950,
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
        "price_pence": 1199,
        "themes": ["necromancy", "locked room", "loyalty", "swords"],
        "mood": ["chaotic", "witty", "propulsive"],
        "pace": "fast",
        "in_stock": True,
        "shop_cat_pick": False,
        "blurb": "Necromancers in space, a haunted house, and a great deal of attitude.",
    },
}


# Reading groups. Each has a real next meeting and a real number of members,
# because a vague invitation is not an invitation.

# How we decide two books are alike. Just counting, no AI.
#
# Count shared themes and multiply by 3. Count shared moods, multiply by 2. Add
# 1 if the genre matches, 0.5 if the pace matches.
#
# Note genre is only worth 1 point, not a requirement. If we filtered by genre,
# The Buried Giant could never be suggested to a Piranesi reader, and it is
# arguably the best match we have.
#
# Why not just ask the AI to suggest something? It would be four lines instead
# of forty, and it would give nicer reasons. But this is free, instant, gives
# the same answer twice in a row, and every suggestion comes with a reason built
# from the actual shared themes. When a merchandising team asks "why did it
# recommend that", we can point at the numbers.

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
    """
    Find a book by title. Returns the book, or None.

    If a partial match hits two books, we return None rather than picking one.
    Same principle as asking which order they meant: when it is ambiguous, do
    not choose.
    """
    needle = (title or "").strip().lower()
    if not needle:
        return None
    for book in CATALOGUE.values():
        if book["title"].lower() == needle:
            return book
    # Try a partial match, but only accept it if exactly one book matches.
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


def shop_cat_picks():
    return [b for b in CATALOGUE.values() if b["shop_cat_pick"] and b["in_stock"]]
