"""Words a sentence cannot end on: the transcript cue for end-of-turn (E5b).

If the caller's latest transcript ends on one of these ("...a lot of", "...because", "um"),
they have not finished, whatever their voice sounds like. Any other last word says nothing,
so the cue can only make the agent wait longer, never reply sooner.

The lists are fixed by grammar class (see ``docs/E5B_SPEC.md``). Words a turn can end on
("yes, I can", "what for", "come in", "hmm", Arabic "بس" = "stop!") are left out on purpose.
"""

from __future__ import annotations

import re


def _words(*groups: str) -> frozenset[str]:
    return frozenset(w for g in groups for w in g.split())


ENGLISH = _words(
    "and or but nor because if unless although whereas than",  # conjunctions
    "a an the my your our their its his",  # articles and possessives
    "of to into onto through via toward towards between among during per",  # need an object
    "i we they he she",  # subject pronouns
    "um uh uhm er erm",  # fillers
)

ARABIC = _words(
    "و أو او لكن ثم لأن لان إذا اذا",  # conjunctions
    "في من إلى الى على عن مع",  # prepositions
    "اللي الذي التي الذين أن",  # relative words and "that"
    "يعني",  # filler ("I mean")
)

UNFINISHED = ENGLISH | ARABIC
_STRIP = re.compile(r"[^\w']+", re.UNICODE)


def last_word(text: str) -> str:
    """Last word of a transcript, lower-cased, without punctuation or quotes."""
    words = [w.strip("'") for w in _STRIP.sub(" ", text).split()]
    words = [w for w in words if w]
    return words[-1].lower() if words else ""


def sounds_unfinished(text: str) -> bool:
    """True if the transcript ends on a word no sentence can end on."""
    return last_word(text) in UNFINISHED
