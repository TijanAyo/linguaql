import logging
import re
from abc import ABC, abstractmethod

from app.config import Settings

logger = logging.getLogger("linguaql.synonyms")

_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

# Very common identifier fragments with no useful/relevant synonyms.
_STOP = {"id", "at", "on", "by", "no", "num", "ts", "uuid", "pk", "fk"}


def split_identifier(name: str) -> list[str]:
    """`total_amountUSD2` -> ['total', 'amount', 'usd', '2']. Pure, deterministic."""
    words: list[str] = []
    for part in re.split(r"[^a-zA-Z0-9]+", name):
        for w in _TOKEN_RE.findall(part):
            words.append(w.lower())
    return [w for w in words if w]


class SynonymExpander(ABC):
    @abstractmethod
    def expand(self, name: str, max_synonyms: int = 5) -> list[str]: ...


class NullExpander(SynonymExpander):
    """No-op (default). Keeps ingestion zero-dependency."""

    def expand(self, name: str, max_synonyms: int = 5) -> list[str]:
        return []


class WordNetExpander(SynonymExpander):
    def __init__(self) -> None:
        import nltk

        self._nltk = nltk
        self._ensure_corpora()
        from nltk.corpus import wordnet as wn

        self._wn = wn
        # touch the corpus so a missing download fails fast at build time
        self._wn.synsets("test")

    def _ensure_corpora(self) -> None:
        # English lemma names only need the core WordNet corpus (omw-1.4 is for
        # cross-language lemmas, which we don't use).
        try:
            self._nltk.data.find("corpora/wordnet")
        except LookupError:
            self._nltk.download("wordnet", quiet=True)

    def _synonyms_for(self, word: str) -> list[str]:
        out: list[str] = []
        for syn in self._wn.synsets(word):
            for lemma in syn.lemmas():
                out.append(lemma.name().replace("_", " ").lower())
        return out

    def expand(self, name: str, max_synonyms: int = 5) -> list[str]:
        words = split_identifier(name)
        seen = set(words)  # never echo the source tokens back
        result: list[str] = []
        for word in words:
            if word in _STOP:
                continue
            for syn in self._synonyms_for(word):
                if syn not in seen:
                    seen.add(syn)
                    result.append(syn)
                    if len(result) >= max_synonyms:
                        return result
        return result


def build_expander(settings: Settings) -> SynonymExpander:
    """Factory with graceful fallback: a missing corpus/package logs a warning
    and falls back to the no-op expander rather than crashing ingestion."""
    if settings.synonyms == "wordnet":
        try:
            return WordNetExpander()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "SYNONYMS=wordnet failed to initialise (%s); synonym expansion "
                "disabled. Is 'nltk' installed and the WordNet corpus available?",
                e,
            )
    return NullExpander()
