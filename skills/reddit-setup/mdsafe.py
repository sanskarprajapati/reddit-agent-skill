"""Make stranger-written text safe to drop into a markdown report."""

import re
from urllib.parse import quote as _urlquote

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MD = re.compile(r"([\\`*_\[\]<>|])")


_AUTOLINK = re.compile(r"(?i)(?<=\w)(://)|\b(www)(\.)")


def md(text):
    """One inert line: no links (not even bare ones a renderer would autolink), no HTML,
    no emphasis, no table breaks."""
    out = _MD.sub(r"\\\1", _CONTROL.sub(" ", str(text))).strip()
    return _AUTOLINK.sub(lambda m: "&#58;//" if m.group(1) else m.group(2) + "&#46;", out)


def link(url):
    """An http(s) URL safe to put in (...), or None for anything else."""
    url = str(url)
    if not re.match(r"^https?://", url):
        return None
    return _urlquote(url, safe=":/?=&#%.,~+-_@!$'*;")


def cite(record_id, url):
    """[id](url) when the URL is safe, else the bare id."""
    safe = link(url)
    return "[%s](%s)" % (md(record_id), safe) if safe else md(record_id)
