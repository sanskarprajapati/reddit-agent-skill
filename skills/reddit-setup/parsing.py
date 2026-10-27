"""Turn numbers and ages as Reddit shows them into plain values.

'1.2k members' -> 1200, '5 hr. ago' -> an ISO time, 'Jan 25, 2008' -> an ISO date.
Anything unclear gives None. A guess would be worse than a gap.
"""

import datetime
import re

_COUNT = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*([km])?\b", re.I)
_AGE = re.compile(r"^(\d{1,6})\s*([a-z]+)\.?\s*(?:ago)?$")
_MONTH_DATE = re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I)
_MONTHS = {m: n for n, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_UNITS = {}
for _names, _secs in ((("s", "sec", "secs", "second", "seconds"), 1),
                      (("m", "min", "mins", "minute", "minutes"), 60),
                      (("h", "hr", "hrs", "hour", "hours"), 3600),
                      (("d", "day", "days"), 86400),
                      (("w", "wk", "wks", "week", "weeks"), 7 * 86400),
                      (("mo", "mos", "month", "months"), 30 * 86400),
                      (("y", "yr", "yrs", "year", "years"), 365 * 86400)):
    for _n in _names:
        _UNITS[_n] = _secs


def iso(moment):
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_count(raw):
    """'1.2k members' -> 1200, '12,345' -> 12345, '-3' -> -3. 'Vote' or '' -> None."""
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return int(raw)
        match = _COUNT.search(str(raw).replace("−", "-"))
        if not match:
            return None
        number = float(match.group(1).replace(",", ""))
        scale = {"k": 1000, "m": 1000000}.get((match.group(2) or "").lower(), 1)
        return int(round(number * scale))
    except (OverflowError, ValueError):
        return None


def parse_iso(raw):
    """An ISO date or date-time as an aware UTC datetime, or None."""
    text = str(raw or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc)


def _month_date(text):
    match = _MONTH_DATE.search(text)
    if not match or match.group(1)[:3].lower() not in _MONTHS:
        return None
    try:
        return datetime.datetime(int(match.group(3)), _MONTHS[match.group(1)[:3].lower()], int(match.group(2)),
                                 tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def parse_age(raw, now):
    """'5 hr. ago', '5h', '2 days ago', 'just now', 'Oct 20, 2026' or an ISO date -> ISO UTC time."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.lower() in ("just now", "now"):
        return iso(now)
    moment = parse_iso(text) or _month_date(text)
    if moment:
        return iso(moment)
    match = _AGE.match(text.lower())
    if not match or match.group(2) not in _UNITS:
        return None
    try:
        return iso(now - datetime.timedelta(seconds=int(match.group(1)) * _UNITS[match.group(2)]))
    except OverflowError:
        return None
