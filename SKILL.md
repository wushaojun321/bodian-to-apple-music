---
name: bodian-to-apple-music
description: 把波点音乐（Bodian，酷我旗下）的个性化推荐每天自动同步成 Apple Music 资料库里按日期命名的播放列表，只保留最近 N 天。适用场景：用户想用波点的推荐但不想看它的广告、想在 Apple Music 里听波点推荐的歌、要部署或排查「波点 → Apple Music」同步（扫码登录波点、获取或更新 Apple Music 的 media-user-token、定时任务、匹配率、429 限流、凭据过期）。触发词：波点、Bodian、Apple Music 歌单同步、每日推荐搬到苹果音乐。
---

# 波点推荐 → Apple Music

所有功能都在 `scripts/b2am.py` 一个命令里。数据目录是 `$BODIAN2AM_HOME`，默认 `~/.bodian2am`，里面有凭据、缓存、日志和配置。下面的命令都在 skill 目录下执行。

## 首次部署（按顺序做，每一步都确认成功再往下）

1. **选机器**：要能长期开机跑定时任务，而且**最好是中国大陆网络**。波点只对大陆开放，海外 IP 下 App 会提示「版本保护」。
2. **装依赖**：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。
   - Ubuntu 如果报 ensurepip 相关错误，先装 `python3.X-venv`。
   - 在国内可以加 `-i https://mirrors.cloud.tencent.com/pypi/simple` 用镜像。
3. **登录波点**：`.venv/bin/python scripts/b2am.py login`。
   - 终端会打印二维码，让用户用**波点 App** 扫一扫（入口在「我的」页右上角），并在手机上点确认。
   - 服务器终端显示不了二维码时，加 `--png qr.png`，把图片传给用户。
4. **拿 Apple Music 凭据**：用户需要先在浏览器里登录 https://music.apple.com，账号要开通 Apple Music 会员。
   - macOS + Chrome：`b2am.py apple-token --from-chrome`。会弹出钥匙串授权，让用户点「允许」。不是默认 Chrome 账户的话加 `--profile "Profile 1"`。
   - 其它情况：让用户在 DevTools → Application → Cookies → `https://music.apple.com` 里复制 `media-user-token` 的值，然后执行 `b2am.py apple-token --set` 并粘贴。
   - 如果凭据是在另一台机器上拿到的，把 `$BODIAN2AM_HOME/apple_token`（权限 600）拷到运行机器上就行。
5. **体检**：`b2am.py doctor`，两项都显示 ✓ 才算准备好。
6. **试跑**：`b2am.py sync --dry-run` 先看匹配结果，没问题再跑 `b2am.py sync`，会生成「波点推荐 MM-DD」歌单。
7. **定时**：`b2am.py cron` 会打印 crontab 配置（主任务加两次补跑），让用户确认后再加进 `crontab -e`。

## 日常维护和排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 输出 `APPLE_AUTH_EXPIRED`，退出码 2 | media-user-token 过期了，网页版一般能用几个月 | 重新登录 music.apple.com，再执行一次 `apple-token` |
| 波点返回非 200，或推荐变得不个性化 | 波点 token 失效 | 重新 `login` |
| 大量 429，跑得很慢 | 请求被 Apple 限流 | 先确认目录搜索没带用户令牌（代码已经这样处理）；再不行就配置 `apple_proxy`，见 references/pitfalls.md |
| 匹配率低 | 翻唱、抖音网络歌在 Apple Music 上本来就没有 | 正常现象，一般在 65%～80%；`logs/日期.json` 里有未匹配明细 |
| 想换推荐来源 | — | `b2am.py modules` 列出首页模块，把 id 写进 config.json 的 `modules` |

配置文件是 `$BODIAN2AM_HOME/config.json`，所有字段都是可选的：`playlist_prefix`（默认「波点推荐」）、`keep_days`（7）、`modules`（[10, 3]）、`fm_rounds`（4）、`miss_retry_days`（7）、`apple_proxy`（null，也可以用环境变量 `APPLE_PROXY`）、`storefront`（默认自动识别）。

## 注意

- 动手前先读 **references/pitfalls.md**，里面是实际踩过的坑，能省很多时间。接口细节在 references/protocol.md。
- 凭据（`apple_token`、`bodian_state.json`）等同于账号权限，不要打印到输出里，不要提交到 git，也不要发给第三方。
- 脚本只删除自己建过的歌单（登记在 `playlists.json` 里），不会碰用户其它歌单。
- 这些都是非官方接口，波点或 Apple 改版后可能失效。出问题时先跑 `doctor` 定位是哪一边坏了。
