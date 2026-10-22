"""Apple Music 网页版 amp-api 客户端：目录搜索 + 资料库播放列表读写。

- 开发者令牌：从 music.apple.com 前端 JS 里取（每次运行都重新抓，不用维护）。
- 用户令牌：浏览器登录 music.apple.com 后的 media-user-token cookie。
"""
import re
import time

import requests

import matcher

BASE = "https://amp-api.music.apple.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")


class AuthExpired(RuntimeError):
    pass


def fetch_developer_token(s: requests.Session) -> str:
    # 不带浏览器 UA 会拿到空页面
    html = s.get("https://music.apple.com/us/browse", headers={"User-Agent": UA}, timeout=30).text
    for path in re.findall(r'/assets/index[^"]*\.js', html):
        js = s.get("https://music.apple.com" + path, headers={"User-Agent": UA}, timeout=60).text
        m = re.search(r"eyJ[\w-]{10,}\.[\w-]{20,}\.[\w-]{20,}", js)
        if m:
            return m.group(0)
    raise RuntimeError("没能从 music.apple.com 前端找到开发者令牌（页面结构可能变了）")


class AppleMusic:
    def __init__(self, media_user_token: str, proxy: str | None = None, storefront: str | None = None):
        proxies = {"http": proxy, "https": proxy} if proxy else {}
        self.s = requests.Session()  # 资料库读写：带用户令牌
        self.s.trust_env = False
        self.s.proxies = proxies
        common = {
            "Authorization": "Bearer " + fetch_developer_token(self.s),
            "Origin": "https://music.apple.com",
            "User-Agent": UA,
        }
        self.s.headers.update({**common, "Media-User-Token": media_user_token})
        # 目录搜索【不带】用户令牌：amp-api 按用户令牌限流，带上时 search 约 40% 返回 429，不带基本为 0
        self.catalog = requests.Session()
        self.catalog.trust_env = False
        self.catalog.proxies = proxies
        self.catalog.headers.update(common)
        self.sf = storefront or self.storefront()

    def req(self, method: str, path: str, session: requests.Session | None = None, **kw):
        # 偶发 429 / 5xx：5/10/20/40/60 秒指数退避
        for attempt in range(6):
            r = (session or self.s).request(method, BASE + path, timeout=30, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            if r.status_code in (401, 403):
                raise AuthExpired(f"{method} {path} -> {r.status_code}：media-user-token 失效，需要重新登录 music.apple.com 并更新")
            r.raise_for_status()
            return r.json() if r.content else {}
        r.raise_for_status()

    def storefront(self) -> str:
        return self.req("GET", "/v1/me/storefront")["data"][0]["id"]

    # ---- 目录 ----
    def search_song(self, name: str, artist: str, duration=None) -> dict | None:
        """在账号所在区域曲库找歌，返回 {id, name, artist}；找不到返回 None。"""
        best, best_score = None, 0
        for term in matcher.search_terms(name, artist):
            data = self.req("GET", f"/v1/catalog/{self.sf}/search", session=self.catalog,
                            params={"term": term, "types": "songs", "limit": 10})
            for song in ((data.get("results") or {}).get("songs") or {}).get("data", []):
                a = song["attributes"]
                sc = matcher.score(name, artist, duration, a.get("name", ""), a.get("artistName", ""),
                                   a.get("durationInMillis"))
                if sc > best_score:
                    best, best_score = {"id": song["id"], "name": a["name"], "artist": a["artistName"]}, sc
            if best_score >= 6:
                break
        return best if best_score >= matcher.MATCH_THRESHOLD else None

    # ---- 资料库播放列表 ----
    def find_playlist(self, name: str) -> str | None:
        path = "/v1/me/library/playlists?limit=100"
        while path:
            data = self.req("GET", path)
            for p in data.get("data", []):
                if p["attributes"].get("name") == name:
                    return p["id"]
            path = data.get("next")
        return None

    def playlist_exists(self, playlist_id: str) -> bool:
        try:
            self.req("GET", f"/v1/me/library/playlists/{playlist_id}")
            return True
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise

    def create_playlist(self, name: str, description: str, song_ids: list[str]) -> str:
        body = {
            "attributes": {"name": name, "description": description},
            "relationships": {"tracks": {"data": [{"id": i, "type": "songs"} for i in song_ids]}},
        }
        return self.req("POST", "/v1/me/library/playlists", json=body)["data"][0]["id"]

    def delete_playlist(self, playlist_id: str) -> None:
        try:
            self.req("DELETE", f"/v1/me/library/playlists/{playlist_id}")
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:  # 已被手动删掉就算了
                raise

    def playlist_tracks(self, playlist_id: str) -> list[dict]:
        out, path = [], f"/v1/me/library/playlists/{playlist_id}/tracks?limit=100"
        while path:
            try:
                data = self.req("GET", path)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:  # 空列表返回 404
                    break
                raise
            out.extend(data.get("data", []))
            path = data.get("next")
        return out

    def clear_playlist(self, playlist_id: str) -> int:
        tracks = self.playlist_tracks(playlist_id)
        for t in tracks:
            self.req("DELETE", f"/v1/me/library/playlists/{playlist_id}/tracks",
                     params={"ids[library-songs]": t["id"], "mode": "all"})
        return len(tracks)

    def add_tracks(self, playlist_id: str, song_ids: list[str]) -> None:
        if song_ids:
            self.req("POST", f"/v1/me/library/playlists/{playlist_id}/tracks",
                     json={"data": [{"id": i, "type": "songs"} for i in song_ids]})
