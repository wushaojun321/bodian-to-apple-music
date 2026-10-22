"""从 macOS 上 Chrome 的 Cookie 库里解密出 music.apple.com 的 media-user-token。

只支持 macOS + Chrome（会弹钥匙串授权「Chrome Safe Storage」，选「允许」）。
其它系统 / 浏览器请手动复制：DevTools → Application → Cookies → https://music.apple.com → media-user-token。
"""
import hashlib
import os
import sqlite3
import subprocess
import sys

CHROME_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")


def read_media_user_token(profile: str = "Default") -> str:
    if sys.platform != "darwin":
        raise RuntimeError("自动读取只支持 macOS，请手动复制 media-user-token")
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    db = os.path.join(CHROME_DIR, profile, "Cookies")
    if not os.path.exists(db):
        raise RuntimeError(f"找不到 {db}，用 --profile 指定 Chrome 账户目录（如 'Profile 1'）")
    # immutable=1：Chrome 开着时库是锁住的，用只读快照方式打开
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    ver = int(con.execute("select value from meta where key='version'").fetchone()[0])
    row = con.execute("select encrypted_value from cookies where host_key like '%music.apple.com' "
                      "and name='media-user-token' order by expires_utc desc").fetchone()
    if not row:
        raise RuntimeError("这个 Chrome 账户里没有 media-user-token：先在 Chrome 里登录 https://music.apple.com")
    enc = row[0]
    if enc[:3] != b"v10":
        raise RuntimeError(f"不认识的 cookie 加密版本 {enc[:3]!r}")
    pw = subprocess.check_output(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"]).strip()
    key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, 16)
    d = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    raw = d.update(enc[3:]) + d.finalize()
    raw = raw[: -raw[-1]]  # PKCS7
    if ver >= 24:  # 新版 Chrome 在明文前加了 32 字节的域名哈希
        raw = raw[32:]
    return raw.decode()
