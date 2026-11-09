"""Bounded multilingual Wikipedia source lookup, returning auditable URLs."""
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re

API_BY_LANGUAGE = {
    "en": "https://en.wikipedia.org/w/api.php",
    "tr": "https://tr.wikipedia.org/w/api.php",
}
TURKISH_MARKERS = set("çğıöşü")
TURKISH_WORDS = {"araştır", "nedir", "nasıl", "için", "kaynak", "yanıt", "cevap", "göre", "üzerine"}
STOP_WORDS = {
    "araştır", "araştırma", "internette", "o", "bu", "şu", "internetten", "webde", "wikipedia",
    "kaynak", "kaynakları", "kaynaklardan", "pasaj", "pasajı", "bul", "bulup",
    "özetle", "özetle", "ver", "göster", "yalnızca", "sadece", "dayandır",
    "dayalı", "yanıtı", "yanıt", "cevabı", "cevap", "nedir", "nasıl", "hakkında",
    "bilgi", "lütfen", "konusunda", "konusundaki", "için", "ile", "ve", "bir",
    "kaynaklarını", "numaralı", "bağlantı", "bağlantılarını", "olarak", "listele", "listeleyin", "doğrulanmış", "pasajlarından", "alınamazsa", "açıkça", "belirt", "bunu",\n    "the", "what", "is", "are", "of", "about", "find", "search", "research",
    "wikipedia", "source", "sources", "passage", "cite", "summarize", "only",
    "based", "on", "please", "give", "show", "and", "for", "to", "from", "url", "urlsini", "sini",
}


def _language(query):
    folded = query.casefold()
    if any(char in TURKISH_MARKERS for char in folded):
        return "tr"
    if any(word in TURKISH_WORDS for word in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]+", folded)):
        return "tr"
    return "en"


def _topic_query(query):
    query = re.sub(r"https?://\S+", " ", query)
    words = re.findall(r"[\wçğıöşüÇĞİÖŞÜ-]+", query.casefold(), flags=re.UNICODE)
    topic = [word for word in words if word not in STOP_WORDS]
    return " ".join(topic[:10])[:160]


def research_sources(query, limit=3, fetch=None):
    if not isinstance(query, str) or not query.strip():
        return []
    limit = max(1, min(int(limit), 5))
    language = _language(query)
    topic = _topic_query(query) or query.strip()[:160]
    api = API_BY_LANGUAGE[language]
    params = {"action": "query", "generator": "search", "gsrsearch": topic[:160],
              "gsrlimit": limit, "prop": "info", "inprop": "url", "format": "json"}
    url = api + "?" + urlencode(params)
    if fetch is None:
        def fetch(url):
            with urlopen(Request(url, headers={"User-Agent": "ResearchAssistant/1.0"}), timeout=6) as response:
                return json.load(response)
    pages = fetch(url).get("query", {}).get("pages", {})
    results = []
    ranked_pages = sorted(pages.values(), key=lambda page: page.get("index", 999999))
    seen = set()
    host = api.split("/", 3)[2]
    for page in ranked_pages:
        title, source = page.get("title"), page.get("fullurl")
        if isinstance(title, str) and isinstance(source, str) and source.startswith("https://" + host + "/wiki/"):
            if source not in seen:
                seen.add(source)
                results.append({"title": title[:200], "url": source})
    return results[:limit]
