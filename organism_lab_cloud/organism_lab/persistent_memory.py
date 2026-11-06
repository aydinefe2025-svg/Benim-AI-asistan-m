"""User-approved local memory for personalized Ollama prompts.

This is retrieval memory, not parameter/weight training. It stores only facts
the user deliberately saves and never auto-learns raw conversations.
"""
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


_TOKEN = re.compile(r"(?i)(?:gsk_[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})")
_WORD = re.compile(r"[\wğüşöçıİĞÜŞÖÇ]{2,}", re.IGNORECASE)
_STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "what",
              "bir", "ve", "ile", "için", "olan", "olarak", "nasıl", "hangi"}
_TR_SUFFIXES = ("lardan", "lerden", "ların", "lerin", "ları", "leri", "lar", "ler",
                "dan", "den", "tan", "ten", "dır", "dir", "dur", "dür", "tır", "tir",
                "tur", "tür", "de", "da", "te", "ta", "in", "ın", "un", "ün",
                "ye", "ya", "e", "a", "i", "ı", "u", "ü")


def _normalised_terms(text):
    terms = set()
    for raw in _WORD.findall(text):
        term = raw.casefold()
        for suffix in _TR_SUFFIXES:
            if term.endswith(suffix) and len(term) - len(suffix) >= 3:
                term = term[:-len(suffix)]
                break
        if term not in _STOPWORDS:
            terms.add(term)
    return terms


def _database(output_dir):
    path = Path(output_dir) / "assistant_memory.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                provenance TEXT NOT NULL DEFAULT 'user-confirmed',
                UNIQUE(topic, content)
            )""")
    return path


def save_memory(output_dir, topic, content):
    """Persist one user-confirmed note; refuse likely credentials and blanks."""
    if not isinstance(topic, str) or not topic.strip() or len(topic.strip()) > 100:
        raise ValueError("Topic must contain 1–100 characters")
    if not isinstance(content, str) or not content.strip() or len(content.strip()) > 4000:
        raise ValueError("Memory must contain 1–4000 characters")
    topic, content = topic.strip(), content.strip()
    if _TOKEN.search(topic) or _TOKEN.search(content):
        raise ValueError("Secret-like text cannot be stored in memory")
    path = _database(output_dir)
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO memories(created_at, topic, content) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), topic, content),
            )
            row = connection.execute(
                "SELECT id FROM memories WHERE topic = ? AND content = ?", (topic, content)
            ).fetchone()
    return {"id": row[0], "topic": topic, "content": content, "provenance": "user-confirmed"}


def list_memories(output_dir, *, limit=100):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Limit must be from 1 to 500")
    path = _database(output_dir)
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT id, created_at, topic, content, provenance FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r[0], "created_at": r[1], "topic": r[2], "content": r[3],
             "provenance": r[4]} for r in rows]


def retrieve_memories(output_dir, query, *, limit=5):
    """Return exact lexical-overlap memories in stable order; no model judge."""
    if not isinstance(query, str) or len(query) > 4000:
        raise ValueError("Query must be text of at most 4000 characters")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Limit must be from 1 to 10")
    terms = _normalised_terms(query)
    if not terms:
        return []
    ranked = []
    for memory in list_memories(output_dir):
        words = _normalised_terms(memory["topic"] + " " + memory["content"])
        score = len(terms & words)
        if score:
            ranked.append((score, memory["id"], memory))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return [item[2] for item in ranked[:limit]]


def augment_with_memory(prompt, memories):
    if not isinstance(prompt, str) or len(prompt) > 12000:
        raise ValueError("Prompt must be text of at most 12000 characters")
    if not memories:
        return prompt
    notes = "\n".join(f"- {item['topic']}: {item['content']}" for item in memories)
    return ("Yanıtlamadan önce aşağıdaki kullanıcı-onaylı kalıcı notları bağlam olarak kullan. "
            "Bunlar bağımsız doğrulanmış değildir; kullanıcı şu an farklı bir şey söylerse güncel mesajı esas al. "
            "Notlardan desteklenmeyen iddiaları çıkarma.\nKALICI NOTLAR:\n" + notes +
            "\n\nGÜNCEL İSTEK:\n" + prompt)
