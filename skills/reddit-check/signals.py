"""What check.py looks for: links, your product (however it is spelled), and self-promotion.

Text is normalised first: full-width letters folded, hidden zero-width characters
removed, and dressed-up dots ("slp[.]io", "slp (dot) io") turned back into dots, so a
link or a name cannot slip past by spelling.
"""

import re
import unicodedata
from urllib.parse import parse_qs, urlparse

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly", "cutt.ly",
              "shorturl.at", "tiny.cc", "rb.gy", "amzn.to", "youtu.be", "geni.us", "t.ly", "lnkd.in", "shorturl.com"}
SHARED_HOSTS = {"github.com", "gitlab.com", "apps.apple.com", "play.google.com", "chrome.google.com",
                "chromewebstore.google.com", "youtube.com", "medium.com", "linktr.ee", "gumroad.com",
                "producthunt.com", "etsy.com", "amazon.com", "patreon.com", "ko-fi.com", "x.com", "twitter.com",
                "instagram.com", "tiktok.com", "linkedin.com", "facebook.com", "notion.site", "reddit.com"}
TRACKING_KEYS = ("tag", "ref", "aff", "affiliate", "utm_source", "utm_medium", "utm_campaign", "referral")
FILE_ENDINGS = {"py", "js", "ts", "tsx", "jsx", "txt", "md", "json", "yaml", "yml", "exe", "png", "jpg", "jpeg",
                "gif", "pdf", "csv", "html", "css", "sh", "zip", "mp3", "mp4", "doc", "docx", "xls", "xlsx", "ppt",
                "pptx", "log", "cfg", "ini", "conf", "dll", "go", "rs", "rb", "java", "cpp", "h", "c", "toml",
                "lock", "bat", "msi", "dmg", "apk", "iso", "svg", "webp", "mov", "wav", "tar", "gz"}

_DOT = re.compile(r"\s*(?:\[\.\]|\(\.\)|\[dot\]|\(dot\)|\{dot\})\s*|\s+dot\s+(?=[a-z]{2,}\b)|\s\.\s(?=[a-z]{2,}\b)",
                  re.I)
_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()\[\]]+")
_BARE = re.compile(r"(?<![@\w.-])((?:[A-Za-z0-9-]+\.)+([a-z]{2,24}))(?![\w-])(/[^\s<>()\[\]]*)?")

PROMO = [re.compile(p, re.I) for p in (
    r"\bi (?:made|built|created|developed|wrote|launched|coded|designed|started) (?:a|an|this|my|our|the)?\s*"
    r"(?:\w+\s+){0,2}(?:app|tool|extension|plugin|site|website|service|product|startup|saas|course|bot|script|"
    r"platform|game|template|newsletter|podcast|company|business)s?\b",
    r"\bi'?m (?:building|making|developing|launching|working on) (?:a|an|my)\b",
    r"\bwe (?:built|made|launched|created|ship|shipped|are building) (?:a|an|our|the)\b",
    r"\b(?:my|our) (?:\w+\s+){0,2}(?:app|product|startup|tool|company|saas|course|newsletter|blog|podcast|extension|"
    r"plugin|repo|shop|store|book|side project|website|service|platform|agency|youtube|twitch|tiktok)\b",
    r"\bmy (?:youtube |twitch |tiktok )?channel\b(?! lock)",
    r"\b(?:co-?)?founder\b", r"\bi'?m the (?:dev|developer|creator|maker|author|owner)\b",
    r"\bshameless (?:self[- ])?plug\b", r"\bfull disclosure\b", r"\bdisclaimer\b", r"\bside project\b",
    r"\bour team\b", r"\bi run (?:a|an)\b", r"\baffiliate\b", r"\breferral\b", r"\buse my (?:link|code)\b",
    r"\b(?:link|it'?s|its) (?:is )?(?:on|in) my (?:profile|bio|github|site|website)\b", r"\blink in (?:my )?bio\b",
    r"\b[dp]m me\b", r"\bpromo code\b", r"\buse code\b", r"\bfree trial\b", r"\bwaitlist\b", r"\bsign up\b",
    r"\bcheck (?:it|this|my \w+) out\b", r"\bcheck out (?:my|our)\b", r"\bsubscribe to my\b", r"\b\d+\s?% off\b",
)]


def normalise(text):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return _DOT.sub(".", text)


def host_of(link):
    link = link if re.match(r"(?i)^https?://", link) else "https://" + link
    try:
        host = (urlparse(link).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def links(text):
    """Every link in normalised text: full URLs, www. ones and bare domains (not file names)."""
    found, spans = [], []
    for m in _URL.finditer(text):
        found.append(m.group(0).rstrip(".,!?;:'\""))
        spans.append(m.span())
    for m in _BARE.finditer(text):
        if any(a <= m.start() < b for a, b in spans) or m.group(2) in FILE_ENDINGS:
            continue
        found.append(m.group(0).rstrip(".,!?;:'\""))
    return found


def _inner(link):
    """Links wrapped inside a link: google.com/url?q=..., redirects and the like."""
    try:
        query = parse_qs(urlparse(link if "://" in link else "https://" + link).query)
    except ValueError:
        return []
    return [v for key in ("q", "url", "u", "target", "redirect", "to") for v in query.get(key, [])]


def tracking(link):
    try:
        query = parse_qs(urlparse(link if "://" in link else "https://" + link).query)
    except ValueError:
        return False
    return any(k.lower() in TRACKING_KEYS or k.lower().startswith("utm_") for k in query)


def _product_key(url):
    """host, or host plus path when the product lives on a shared site like github.com."""
    host = host_of(url)
    if host in SHARED_HOSTS:
        path = urlparse(url if "://" in url else "https://" + url).path.rstrip("/").lower()
        return host + path if path else ""
    return host


def links_product(text, product_url):
    key = _product_key(product_url) if product_url else ""
    if not key:
        return False
    host = key.split("/")[0]
    pattern = re.compile(r"(?<![\w-])(?:[\w-]+\.)*%s%s(?![\w-])" % (
        re.escape(host), re.escape(key[len(host):])), re.I)
    every = links(text)
    every += [i for link in every for i in _inner(link)]
    return bool(pattern.search(text)) or any(pattern.search(link) for link in every)


def names_product(text, name):
    """Your product's name, spaced, hyphenated, joined up or plural."""
    letters = [ch for ch in str(name or "").lower() if ch.isalnum()]
    if len(letters) < 2:
        return False
    body = r"[\W_]*".join(re.escape(ch) for ch in letters)
    if len(letters) < 3:
        return bool(re.search(r"(?<![^\W_])%s(?![^\W_])" % body, text, re.I))
    return bool(re.search(r"(?<![^\W_])%s(?:e?s)?(?![^\W_])" % body, text, re.I))


def promo_phrases(text):
    return sorted({m.group(0).lower() for p in PROMO for m in p.finditer(text)})


def shouting(text):
    """A run of three capitalised words, !!!, or mostly capitals. Acronyms alone are fine."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    run = best = 0
    for w in words:
        run = run + 1 if w.isupper() else 0
        best = max(best, run)
    letters = [ch for ch in text if ch.isalpha()]
    mostly = len(letters) >= 20 and sum(ch.isupper() for ch in letters) / len(letters) > 0.5
    return best >= 3 or "!!!" in text or mostly
