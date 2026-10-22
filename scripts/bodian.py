"""波点音乐 bd-api 最小客户端：签名、扫码登录、个性化推荐。

非官方接口，协议参考 https://github.com/Wuyuhang0729/bobo-source 的公开文档，本文件为独立实现。
"""
import hashlib
import json
import time
import uuid
from urllib.parse import quote_plus, urlencode

import requests

API = "https://bd-api.kuwo.cn"
SALT = "kuwotest"
QR_URL = "https://bodian-oia.kuwo.cn/bodian/download.html?pageName=login_pc&pt=3&id={}"

# 首页模块 id（来自 /api/service/home/index 的 moduleList）
MODULE_SIMILAR = 10   # 心动收藏相似推荐
MODULE_ENCOUNTER = 3  # 偶遇心动单曲


class BodianError(RuntimeError):
    pass


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def sign(path: str, params: list, body: str = "") -> str:
    """seed = "kuwotest" + 排序后的(urlencode(params) 中的字母数字字符) [+ md5(body+"kuwotest")]；sign = md5(seed + path)。

    urlencode 必须是 Python quote_plus 语义，body 必须是紧凑 JSON（与发送的字节完全一致）。
    """
    alnum = sorted(c for c in urlencode(params, quote_via=quote_plus) if c.isascii() and c.isalnum())
    seed = SALT + "".join(alnum)
    if body:
        seed += md5(body + SALT)
    return md5(seed + path)


class Bodian:
    def __init__(self, state: dict):
        """state 至少会被写入 devid；登录后包含 uid / token / nickname。调用方负责持久化。"""
        self.state = state
        self.state.setdefault("devid", uuid.uuid4().hex)
        self.s = requests.Session()
        self.s.trust_env = False  # 波点只对大陆开放，直连
        self.s.headers.update({
            # 伪装波点 Windows 客户端；缺 devid/qimei36 会返回 402
            "user-agent": "Dart/3.3 (dart:io)",
            "plat": "win",
            "api-ver": "application/json",
            "channel": "W1",
            "brand": "Windows 11 Pro for Workstations",
            "net": "wifi",
            "content-type": "application/json",
            "ver": "1.1.5",
            "svrver": "13",
            "devid": self.state["devid"],
            "qimei36": self.state["devid"],
        })

    @property
    def uid(self) -> str:
        return str(self.state.get("uid") or "-1")

    @property
    def token(self) -> str:
        return self.state.get("token") or ""

    @property
    def logged_in(self) -> bool:
        return self.uid != "-1" and bool(self.token)

    def call(self, path: str, params: list, method: str = "GET", body: dict | None = None):
        params = list(params)
        body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        params.append(("timestamp", str(int(time.time() * 1000))))
        params.append(("sign", sign(path, params, body_text)))
        url = f"{API}{path}?{urlencode(params, quote_via=quote_plus)}"
        r = self.s.request(method, url, data=body_text.encode() if body_text else None, timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 200:
            raise BodianError(f"{path} -> code={j.get('code')} msg={j.get('msg') or j.get('message')}")
        return j.get("data")

    # ---- 扫码登录 ----
    def qr_code(self) -> str:
        return self.call("/api/ucenter/login/qrCode", [("uid", "-1"), ("token", "")])["qrCode"]

    def qr_status(self, qr: str) -> int:
        """1=未扫 2=已扫待确认 3=已确认"""
        data = self.call("/api/ucenter/login/qrCodeStatus", [("qrCode", qr), ("uid", "-1")]) or {}
        return int(data.get("status") or 0)

    def login_with_qr(self, qr: str) -> dict:
        # 注意：这个 POST 也要签名；用户 id 字段是 data.id，不是 uid
        data = self.call("/api/ucenter/users/login", [], method="POST", body={"authType": 10, "qrCode": qr})
        uid = data.get("id") or data.get("uid")
        if not uid or not data.get("token"):
            raise BodianError("登录已确认，但没有返回 id/token")
        self.state.update(uid=str(uid), token=data["token"],
                          nickname=(data.get("userInfo") or {}).get("nickname"))
        return data

    # ---- 推荐 ----
    def _auth(self) -> list:
        return [("uid", self.uid), ("token", self.token)]

    def home_index(self) -> list:
        return (self.call("/api/service/home/index", self._auth()) or {}).get("moduleList") or []

    def home_module(self, module_id: int) -> list:
        """注意：每次请求都会返回新的一批，并不是「日更」固定内容。"""
        data = self.call("/api/service/home/module", [("moduleId", str(module_id))] + self._auth()) or {}
        return data.get("musicList") or []

    def personal_fm(self, rounds: int) -> list:
        out = []
        for i in range(rounds):
            data = self.call("/api/service/music/recommendList", [
                ("fg", "1"), ("lock", "0"), ("recoMode", "normal"),
                ("scrollNum", str(i)), ("totalNum", str(len(out))),
                # 固定值会反复给同一批，每轮换一个
                ("lastColdStartTime", str(int(time.time() * 1000) - i)),
            ] + self._auth()) or {}
            out.extend(data.get("musicList") or [])
        return out


def simplify(song: dict) -> dict:
    artist = song.get("artist") or "&".join(a.get("name", "") for a in song.get("artists") or [])
    return {
        "id": str(song.get("id") or song.get("musicId") or ""),
        "name": song.get("name") or song.get("songName") or "",
        "artist": artist or "",
        "album": song.get("album") or "",
        "duration": song.get("duration"),
    }
