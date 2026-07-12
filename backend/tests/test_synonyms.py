"""Deterministic synonym expansion (TSD §3d)."""
import pytest

from app.config import Settings
from app.core.ingest import _composite_doc
from app.core.synonyms import (
    NullExpander,
    WordNetExpander,
    build_expander,
    split_identifier,
)


def _wordnet_available() -> bool:
    try:
        WordNetExpander()
        return True
    except Exception:
        return False


wordnet_only = pytest.mark.skipif(
    not _wordnet_available(), reason="nltk WordNet corpus unavailable"
)


# --------------------------------------------------------------------------- #
# Identifier tokenizer (pure — always runs)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,expected",
    [
        ("user_id", ["user", "id"]),
        ("totalAmount", ["total", "amount"]),
        ("created_at", ["created", "at"]),
        ("id", ["id"]),
        ("price_USD_2", ["price", "usd", "2"]),
    ],
)
def test_split_identifier(name, expected):
    assert split_identifier(name) == expected


def test_null_expander_returns_nothing():
    assert NullExpander().expand("revenue") == []


def test_build_expander_defaults_to_null():
    assert isinstance(build_expander(Settings(synonyms="none")), NullExpander)


def test_composite_doc_includes_synonyms():
    doc = _composite_doc("orders", "amount", "numeric", ["10", "20"], ["income", "sum"])
    assert "Synonyms: income, sum" in doc
    assert "Column: amount" in doc


def test_composite_doc_without_synonyms():
    doc = _composite_doc("orders", "amount", "numeric", [], [])
    assert "Synonyms: n/a" in doc


# --------------------------------------------------------------------------- #
# WordNet expander (skipped if the corpus isn't installed)
# --------------------------------------------------------------------------- #
@wordnet_only
def test_wordnet_expands_known_word():
    syns = WordNetExpander().expand("revenue")
    assert syns  # non-empty
    assert "gross" in syns or "income" in syns


@wordnet_only
def test_wordnet_is_deterministic():
    exp = WordNetExpander()
    assert exp.expand("amount") == exp.expand("amount")


@wordnet_only
def test_wordnet_excludes_source_tokens_and_stopwords():
    syns = WordNetExpander().expand("user_id")
    # 'id' is a stopword (skipped); source tokens never echoed back
    assert "user" not in syns and "id" not in syns


@wordnet_only
def test_build_expander_wordnet_returns_expander():
    assert isinstance(build_expander(Settings(synonyms="wordnet")), WordNetExpander)
