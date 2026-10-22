#!/usr/bin/env python3
"""波点推荐 → Apple Music 播放列表。

用法：
  b2am.py login                      扫码登录波点（终端打印二维码）
  b2am.py apple-token --from-chrome  从 macOS Chrome 读取 Apple Music 登录凭据
  b2am.py apple-token --set          粘贴 media-user-token（从标准输入读）
  b2am.py doctor                     体检：两边登录、接口、代理是否正常
  b2am.py sync [--dry-run] [--if-missing]
  b2am.py cron [--hour 7]            打印 crontab 配置
  b2am.py modules                    列出波点首页模块（找新的推荐来源）

数据目录：$BODIAN2AM_HOME，默认 ~/.bodian2am
"""
import argparse
import datetime
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

import applemusic  # noqa: E402
import bodian  # noqa: E402

HOME = os.path.expanduser(os.environ.get("BODIAN2AM_HOME", "~/.bodian2am"))
DEFAULTS = {
    "playlist_prefix": "波点推荐",   # 歌单名：「波点推荐 10-21」
    "keep_days": 7,                  # 只保留最近几天的歌单
    "modules": [bodian.MODULE_SIMILAR, bodian.MODULE_ENCOUNTER],
    "fm_rounds": 4,                  # 私人 FM 拉几轮（每轮约 6 首），0 表示不要
    "miss_retry_days": 7,            # 没匹配上的歌，隔几天再搜一次
    "apple_proxy": None,             # 例如 "http://127.0.0.1:7890"，也可用环境变量 APPLE_PROXY
    "storefront": None,              # 默认自动识别账号区域
}


# ---------- 文件 ----------
def path(name: str) -> str:
    return os.path.join(HOME, name)


def load_json(name: str, default):
    try:
        with open(path(name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(name: str, data, private: bool = False) -> None:
    os.makedirs(HOME, exist_ok=True)
    tmp = path(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path(name))


def config() -> dict:
    cfg = {**DEFAULTS, **load_json("config.json", {})}
    cfg["apple_proxy"] = os.environ.get("APPLE_PROXY", cfg["apple_proxy"]) or None
    return cfg


def apple_token() -> str:
    try:
        with open(path("apple_token")) as f:
            return f.read().strip()
    except FileNotFoundError:
        sys.exit("还没有 Apple Music 凭据：先运行 b2am.py apple-token --from-chrome（或 --set）")


def new_apple(cfg: dict) -> applemusic.AppleMusic:
    return applemusic.AppleMusic(apple_token(), proxy=cfg["apple_proxy"], storefront=cfg["storefront"])


def new_bodian() -> bodian.Bodian:
    return bodian.Bodian(load_json("bodian_state.json", {}))


# ---------- login ----------
def cmd_login(args) -> int:
    import qrcode

    b = new_bodian()
    qr = b.qr_code()
    url = bodian.QR_URL.format(qr)
    q = qrcode.QRCode(border=1)
    q.add_data(url)
    try:
        q.print_ascii(invert=True)
    except UnicodeEncodeError:  # 输出被重定向到非 UTF-8 编码时打印不了方块字符
        print("（终端无法显示二维码，请看图片）")
    png = args.png or (path("login_qr.png") if os.name == "nt" else None)
    if png:
        os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
        q.make_image().save(png)
        print(f"二维码图片：{png}")
        if os.name == "nt":  # Windows 老控制台的方块字符常常显示错位，直接打开图片
            os.startfile(png)
    print("用手机波点 App 扫一扫（「我的」页右上角），并在手机上确认登录。5 分钟内有效……")
    last = None
    for _ in range(150):
        st = b.qr_status(qr)
        if st != last and st == 2:
            print("已扫码，等待手机上确认……")
        last = st
        if st == 3:
            b.login_with_qr(qr)
            save_json("bodian_state.json", b.state, private=True)
            print(f"登录成功：{b.state.get('nickname')}")
            return 0
        time.sleep(2)
    print("超时了，重新运行 login")
    return 1


# ---------- apple-token ----------
def cmd_apple_token(args) -> int:
    if args.from_chrome:
        import chrome_cookie

        token = chrome_cookie.read_media_user_token(args.profile)
    else:
        print("粘贴 media-user-token 后回车：", file=sys.stderr)
        token = sys.stdin.readline().strip()
    if len(token) < 100:
        sys.exit("看起来不像 media-user-token（太短了）")
    os.makedirs(HOME, exist_ok=True)
    with open(path("apple_token"), "w") as f:
        f.write(token)
    os.chmod(path("apple_token"), 0o600)
    try:
        am = new_apple(config())
        print(f"已保存，验证通过，账号区域：{am.sf}")
    except Exception as e:
        print(f"已保存，但验证失败：{e}")
        return 1
    return 0


# ---------- doctor ----------
def cmd_doctor(args) -> int:
    cfg = config()
    ok = True
    print(f"数据目录：{HOME}")
    print(f"Apple 代理：{cfg['apple_proxy'] or '无（直连）'}")
    b = new_bodian()
    if not b.logged_in:
        print("✗ 波点：未登录 → b2am.py login")
        ok = False
    else:
        try:
            n = len(b.home_module(bodian.MODULE_SIMILAR))
            print(f"✓ 波点：{b.state.get('nickname')}，推荐接口正常（{n} 首）")
        except Exception as e:
            print(f"✗ 波点：接口失败 {e}（token 失效就重新 login；海外 IP 可能被拒）")
            ok = False
    try:
        am = new_apple(cfg)
        hit = am.search_song("晴天", "周杰伦")
        print(f"✓ Apple Music：区域 {am.sf}，资料库可访问，搜索正常（{hit and hit['name']}）")
    except applemusic.AuthExpired as e:
        print(f"✗ Apple Music：{e}")
        ok = False
    except Exception as e:
        print(f"✗ Apple Music：{type(e).__name__} {e}")
        ok = False
    return 0 if ok else 1


# ---------- sync ----------
def collect(b: bodian.Bodian, cfg: dict) -> list[dict]:
    raw = []
    for mid in cfg["modules"]:
        try:
            raw += b.home_module(int(mid))
        except Exception as e:
            print(f"模块 {mid} 拉取失败：{e}")
    if cfg["fm_rounds"]:
        try:
            raw += b.personal_fm(int(cfg["fm_rounds"]))
        except Exception as e:
            print(f"私人 FM 拉取失败：{e}")
    seen, songs = set(), []
    for s in map(bodian.simplify, raw):
        if s["id"] and s["name"] and s["id"] not in seen:
            seen.add(s["id"])
            songs.append(s)
    return songs


def cmd_sync(args) -> int:
    cfg = config()
    day = datetime.date.today()
    today = day.isoformat()
    reg = load_json("playlists.json", {})  # {日期: 播放列表 id}，只清理这里登记过的
    if args.if_missing and today in reg:
        print("今天的歌单已存在，跳过")
        return 0

    b = new_bodian()
    if not b.logged_in:
        sys.exit("波点未登录：先运行 b2am.py login")
    songs = collect(b, cfg)
    if not songs:
        sys.exit("没拉到任何推荐（波点 token 可能失效，运行 doctor 看看）")
    am = new_apple(cfg)

    cache = load_json("match_cache.json", {})  # {波点 id: {id,name,artist} | {miss: 日期}}
    retry_before = (day - datetime.timedelta(days=int(cfg["miss_retry_days"]))).isoformat()
    matched, missed, failed, ids = [], [], [], []
    for s in songs:
        hit = cache.get(s["id"])
        if hit is None or (hit.get("miss") and hit["miss"] < retry_before):
            try:
                found = am.search_song(s["name"], s["artist"], s["duration"])
            except requests.HTTPError as e:  # 退避后仍失败：跳过这首，不缓存
                failed.append(s)
                print(f"  搜索失败：{s['name']} {e}")
                continue
            hit = found or {"miss": today}
            cache[s["id"]] = hit
            time.sleep(0.5)
        if hit.get("id"):
            if hit["id"] not in ids:
                ids.append(hit["id"])
                matched.append({**s, "apple": hit})
        else:
            missed.append(s)
    save_json("match_cache.json", cache)

    summary = f"波点推荐 {today}：匹配 {len(matched)}/{len(songs)} 首" + (f"，{len(failed)} 首搜索失败" if failed else "")
    if args.dry_run:
        print(summary + "（dry-run，未写入 Apple Music）")
        for m in matched:
            print(f"  ✓ {m['name']} / {m['artist']}  →  {m['apple']['name']} / {m['apple']['artist']}")
        for s in missed:
            print(f"  ✗ {s['name']} / {s['artist']}")
        return 0

    name = f"{cfg['playlist_prefix']} {day:%m-%d}"
    pid = reg.get(today)
    if pid and am.playlist_exists(pid):  # 同一天重跑：覆盖当天歌单
        am.clear_playlist(pid)
        am.add_tracks(pid, ids)
    else:
        pid = am.create_playlist(name, summary, ids)
    reg[today] = pid
    save_json("playlists.json", reg)

    cutoff = (day - datetime.timedelta(days=int(cfg["keep_days"]) - 1)).isoformat()
    for d in sorted(reg):
        if d < cutoff:
            am.delete_playlist(reg.pop(d))
            print(f"删除过期歌单：{d}")
    save_json("playlists.json", reg)

    os.makedirs(path("logs"), exist_ok=True)
    save_json(os.path.join("logs", f"{today}.json"),
              {"date": today, "playlist": pid, "matched": matched, "missed": missed, "failed": failed})
    print(summary + f" → 「{name}」")
    for s in missed:
        print(f"  未匹配：{s['name']} / {s['artist']}")
    return 0


# ---------- cron / modules ----------
def cmd_cron(args) -> int:
    py = sys.executable
    me = os.path.abspath(__file__)
    if os.name == "nt":  # Windows：任务计划程序
        def tr(extra: str) -> str:
            return f'"{py}" "{me}" sync{extra}'.replace('"', '\\"')  # /TR 参数内部的引号要转义成 \"
        print("REM 在「命令提示符」里执行（电脑要开机，且在设定时间处于唤醒状态）：")
        if "BODIAN2AM_HOME" in os.environ:  # 自定义数据目录：设成用户级环境变量，计划任务才读得到
            print(f'setx BODIAN2AM_HOME "{HOME}"')
        print(f'schtasks /Create /F /SC DAILY /ST {args.hour:02d}:00 /TN "b2am-sync" /TR "{tr("")}"')
        for h in (args.hour + 2, args.hour + 5):
            print(f'schtasks /Create /F /SC DAILY /ST {h:02d}:00 /TN "b2am-sync-retry-{h}" /TR "{tr(" --if-missing")}"')
        print('REM 删除：schtasks /Delete /F /TN "b2am-sync"（补跑任务同理）')
        return 0
    env = f"BODIAN2AM_HOME={HOME}"
    log = path("cron.log")
    # flock 防止补跑和主任务重叠；macOS 默认没有 flock（brew install flock），没有就不加锁
    lock = f"flock -n {path('.lock')}" if shutil.which("flock") else ""
    print("# 加到 crontab -e（时间是机器本地时区）：")
    print(f"0 {args.hour} * * * {env} {lock} {py} {me} sync >> {log} 2>&1")
    print(f"0 {args.hour + 2},{args.hour + 5} * * * {env} {lock} {py} {me} sync --if-missing >> {log} 2>&1")
    return 0


def cmd_modules(args) -> int:
    for m in new_bodian().home_index():
        print(m.get("id"), m.get("type"), m.get("name") or m.get("moduleName"))
    return 0


def main() -> int:
    # Windows 计划任务等无控制台场景下 stdout 是 GBK，✓ 之类字符会抛 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="波点推荐 → Apple Music 播放列表")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("login", help="扫码登录波点")
    sp.add_argument("--png", help="同时把二维码存成图片")
    sp = sub.add_parser("apple-token", help="保存 Apple Music 的 media-user-token")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-chrome", action="store_true", help="从 macOS Chrome 读取")
    g.add_argument("--set", action="store_true", help="从标准输入粘贴")
    sp.add_argument("--profile", default="Default", help="Chrome 账户目录名，默认 Default")
    sub.add_parser("doctor", help="体检")
    sp = sub.add_parser("sync", help="同步今天的推荐")
    sp.add_argument("--dry-run", action="store_true", help="只匹配不写入")
    sp.add_argument("--if-missing", action="store_true", help="今天已同步过就跳过（给补跑用）")
    sp = sub.add_parser("cron", help="打印 crontab 配置")
    sp.add_argument("--hour", type=int, default=7)
    sub.add_parser("modules", help="列出波点首页模块")
    args = p.parse_args()
    handler = {"login": cmd_login, "apple-token": cmd_apple_token, "doctor": cmd_doctor, "sync": cmd_sync,
               "cron": cmd_cron, "modules": cmd_modules}[args.cmd]
    try:
        return handler(args)
    except applemusic.AuthExpired as e:
        print(f"APPLE_AUTH_EXPIRED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
