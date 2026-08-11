from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from w3lib.url import canonicalize_url as w3lib_canonicalize_url
except Exception:  # pragma: no cover
    w3lib_canonicalize_url = None


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "gbraid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "igshid",
    "ref",
    "spm",
    "vero_id",
    "yclid",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return ""

    split = urlsplit(url.strip())
    query_pairs = []
    for key, value in parse_qsl(split.query, keep_blank_values=False):
        lower_key = key.lower()
        if lower_key.startswith("utm_") or lower_key in TRACKING_PARAMS:
            continue
        query_pairs.append((key, value))

    cleaned = urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            split.path or "/",
            urlencode(sorted(query_pairs), doseq=True),
            "",
        )
    )

    if w3lib_canonicalize_url:
        return w3lib_canonicalize_url(cleaned, keep_blank_values=False)
    return cleaned


def resource_type_for_url(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if host in {"youtu.be", "www.youtu.be"} or host.endswith("youtube.com"):
        return "youtube"
    if url.startswith(("http://", "https://")):
        return "webpage"
    return "unknown"
