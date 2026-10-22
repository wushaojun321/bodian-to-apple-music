"""歌名 / 歌手归一化与打分，用于把波点歌曲对到 Apple Music 曲目。"""
import re
import unicodedata

try:  # 可选：繁体结果（港台区）转简体再比
    import opencc

    _t2s = opencc.OpenCC("t2s").convert
except ImportError:  # pragma: no cover
    _t2s = lambda s: s  # noqa: E731

_BRACKETS = re.compile(r"[\(\[（【].*?[\)\]）】]")
_SUFFIX = re.compile(r"\s*-\s*(live|伴奏|remix|dj).*$", re.I)
_PUNCT = re.compile(r"[\s·'’\".,，。!！?？&/、_\-]+")


def norm(s: str) -> str:
    s = _t2s(unicodedata.normalize("NFKC", s or "")).lower()
    s = _BRACKETS.sub("", s)  # 去掉 (Live) 【伴奏】 (电视剧《xx》主题曲) 之类
    s = _SUFFIX.sub("", s)
    return _PUNCT.sub("", s)


def split_artists(a: str) -> list[str]:
    parts = re.split(r"[&/、,，]| feat\.? | ft\.? ", a or "", flags=re.I)
    return [x for x in (norm(p) for p in parts) if x]


def lead_artist(a: str) -> str:
    return re.split(r"[&/、,，]", a or "")[0].strip()


def search_terms(name: str, artist: str) -> list[str]:
    """先用完整歌名搜，再用去掉括号副标题的歌名搜。"""
    terms = [f"{name} {lead_artist(artist)}".strip()]
    bare = re.sub(r"\s*[\(（].*?[\)）]", "", name).strip()
    if bare and bare != name:
        terms.append(f"{bare} {lead_artist(artist)}".strip())
    return terms


def score(want_name: str, want_artist: str, want_duration, got_name: str, got_artist: str, got_ms) -> int:
    """歌名完全一致 3 分 / 包含 1 分；歌手对上 3 分；时长差 ≤3 秒 2 分。≥5 分才算匹配。"""
    wn, gn = norm(want_name), norm(got_name)
    if wn == gn:
        s = 3
    elif wn and gn and (wn in gn or gn in wn):
        s = 1
    else:
        return 0
    ga = norm(got_artist)
    if ga and any(a in ga or ga in a for a in split_artists(want_artist)):
        s += 3
    if want_duration and got_ms and abs(got_ms / 1000 - float(want_duration)) <= 3:
        s += 2
    return s


MATCH_THRESHOLD = 5
