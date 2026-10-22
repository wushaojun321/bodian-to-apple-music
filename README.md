# 波点推荐 → Apple Music

每天自动把**波点音乐**给你的个性化推荐，同步成 **Apple Music** 资料库里按日期命名的歌单，例如「波点推荐 10-21」，只保留最近 7 天。

用波点的推荐算法，在 Apple Music 里听，没有开屏广告，也没有弹窗。

它既是一个 [Claude Code](https://claude.com/claude-code) Skill（让 Claude 帮你部署和排查），也可以当普通命令行工具单独使用。

```
波点 App 扫码登录 ─┐                        ┌─ 每天 7:00 定时运行
                   ▼                        ▼
   波点推荐接口（心动相似 / 偶遇单曲 / 私人 FM，约 50 首）
                   │
                   ▼  在你账号所在区域的 Apple Music 曲库里逐首匹配（命中率约 65%～80%）
                   │
   Apple Music 资料库：新建「波点推荐 MM-DD」，删除 7 天前的歌单
                   │
                   ▼
        iPhone / Mac「音乐」App 里直接听（iCloud 自动同步）
```

## 你需要准备

- 一个**波点音乐**账号（手机上装好 App）。
- 一个开通了 **Apple Music 会员**的 Apple ID。
- 一台能**长期开机**、能跑定时任务的机器：自己的电脑、NAS 或云服务器都可以。

## 环境要求

| 项目 | 要求 |
|---|---|
| Python | **3.10 及以上** |
| 网络 | 运行同步的机器**最好在中国大陆网络下**，因为波点只对大陆开放。Apple Music 那边国内直连就能用 |
| 依赖 | `requests`、`qrcode`、`opencc-python-reimplemented`；macOS 自动读取 Chrome 凭据时还需要 `cryptography`（见 `requirements.txt`） |

| 系统 | 扫码登录波点 | 获取 Apple 凭据 | 定时任务 |
|---|---|---|---|
| **Linux**（服务器 / NAS） | 终端直接显示二维码，也可以加 `--png` 存成图片 | 手动粘贴；也可以在 Mac 上取好后拷过来 | cron（`b2am.py cron` 生成配置） |
| **macOS** | 终端二维码 | ✅ `--from-chrome` 自动读取 | cron |
| **Windows** 10/11 | 自动打开二维码图片 | 手动粘贴（Chrome 127 起用了应用绑定加密，外部程序解不开） | 任务计划程序（`b2am.py cron` 生成 schtasks 命令） |

> Windows 适配是按 Windows 的行为编写的，并用模拟输出检查过，**但还没有在 Windows 真机上完整跑过**。遇到问题欢迎提 Issue。

## 安装

**作为 Claude Code Skill 使用**（推荐。装好后对 Claude 说「帮我部署波点同步 Apple Music」，它会一步步带你完成）：

```bash
git clone https://github.com/wushaojun321/bodian-to-apple-music ~/.claude/skills/bodian-to-apple-music
```

**单独当命令行工具使用**：

```bash
git clone https://github.com/wushaojun321/bodian-to-apple-music
cd bodian-to-apple-music
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip install -r requirements.txt
# 国内网络慢的话可以加：-i https://mirrors.cloud.tencent.com/pypi/simple
```

下面的命令以 Linux/macOS 为例。Windows 上把 `.venv/bin/python` 换成 `.venv\Scripts\python`。

## 快速开始

```bash
# 1. 扫码登录波点：用手机波点 App 扫一扫（「我的」页右上角），在手机上确认
.venv/bin/python scripts/b2am.py login

# 2. 保存 Apple Music 凭据（先在浏览器登录 https://music.apple.com）
.venv/bin/python scripts/b2am.py apple-token --from-chrome   # 仅 macOS + Chrome
.venv/bin/python scripts/b2am.py apple-token --set           # 其它情况：粘贴 media-user-token

# 3. 体检，两项都是 ✓ 再往下
.venv/bin/python scripts/b2am.py doctor

# 4. 先看匹配效果（不会写入），再正式同步
.venv/bin/python scripts/b2am.py sync --dry-run
.venv/bin/python scripts/b2am.py sync

# 5. 生成定时任务配置，复制到 crontab -e，Windows 下在 cmd 里执行
.venv/bin/python scripts/b2am.py cron
```

**手动获取 media-user-token**：在浏览器登录 music.apple.com 后按 F12 → 「Application」（应用）→ Cookies → `https://music.apple.com`，复制 `media-user-token` 那一行的值。

**在服务器上运行，但凭据在 Mac 上取**：在 Mac 上运行 `apple-token --from-chrome`，然后把 `~/.bodian2am/apple_token` 拷到服务器的同一位置，权限设为 600。

## 配置（可选）

所有数据放在 `$BODIAN2AM_HOME`，默认 `~/.bodian2am`。在里面新建 `config.json` 可以覆盖默认值：

```json
{
  "playlist_prefix": "波点推荐",
  "keep_days": 7,
  "modules": [10, 3],
  "fm_rounds": 4,
  "miss_retry_days": 7,
  "apple_proxy": null,
  "storefront": null
}
```

| 字段 | 说明 |
|---|---|
| `playlist_prefix` | 歌单名前缀，最终名字形如「波点推荐 10-21」 |
| `keep_days` | 保留最近几天的歌单，更早的自动删除（只删本工具建的歌单） |
| `modules` | 推荐来源，用的是波点首页模块 id：10 心动收藏相似推荐，3 偶遇心动单曲。`b2am.py modules` 能列出全部模块 |
| `fm_rounds` | 私人 FM 拉几轮，每轮约 6 首，0 表示不要 |
| `miss_retry_days` | 没匹配上的歌，隔几天再搜一次（Apple 可能上新） |
| `apple_proxy` | Apple 请求用的代理，比如 `http://127.0.0.1:7890` 或 `socks5h://...`；也可以用环境变量 `APPLE_PROXY`。一般不需要 |
| `storefront` | Apple Music 区域，默认自动识别账号所在区域 |

数据目录里的其它文件：

| 文件 | 内容 |
|---|---|
| `bodian_state.json` | 波点登录态（敏感） |
| `apple_token` | Apple 凭据（敏感） |
| `playlists.json` | 本工具建过的歌单登记 |
| `match_cache.json` | 匹配缓存 |
| `logs/日期.json` | 每天的匹配明细，包括没匹配上的歌 |
| `cron.log` | 定时任务的输出 |

## 常见问题

**过一段时间就不同步了？**
看 `cron.log`：
- 出现 `APPLE_AUTH_EXPIRED`：Apple 凭据过期了，网页版一般能用几个月。重新登录 music.apple.com 后，再执行一次 `apple-token`。
- 波点报错：重新 `login`。
- 不确定是哪边的问题：先跑 `doctor`。

**为什么有些歌没加进去？**
Apple Music 上没有，最常见的是翻唱、抖音网络歌、DJ 版。每天的 `logs/日期.json` 里能看到具体是哪些歌。

**手机上怎么让今天的歌单排在最前面？**
在「资料库 → 播放列表」右上角的排序里选「最近添加」。

**会把我的资料库弄乱吗？**
不会。歌只加进歌单，不会进「资料库 → 歌曲」。工具也只删除自己建过的歌单。

**波点的「每日推荐」几点更新？**
这几个推荐接口每次请求都返回新的一批，没有固定的更新时间，几点运行都行。

更多实际踩过的坑，比如 429 限流的真正原因、iTunes 搜索 API 搜不到中国区、Chrome Cookie 解密的细节，见 [references/pitfalls.md](references/pitfalls.md)。接口细节见 [references/protocol.md](references/protocol.md)。

## 免责声明

- 本项目使用的波点 `bd-api` 和 Apple Music 网页版 `amp-api` 都是**非官方接口**，随时可能失效。本项目与波点音乐、酷我、腾讯音乐、Apple 均无关联。
- 本项目**只读取你自己账号的推荐列表，并在你自己的 Apple Music 资料库里建歌单**，不下载、不传播任何音频，听歌仍需要你自己的 Apple Music 会员。
- 请仅用于个人学习和自用，遵守各平台的服务条款。凭据文件等同于账号权限，请妥善保管，不要分享给他人。

## 致谢与引用

| 项目 | 协议 | 本项目用到了什么 |
|---|---|---|
| [Wuyuhang0729/bobo-source](https://github.com/Wuyuhang0729/bobo-source) | AGPL-3.0 | 参考了它公开的波点协议文档（`any-listen/实现文档.md`、`folia/mods/bodian-source/NOTES.md`）：签名算法、请求头、扫码登录流程、首页模块与私人 FM 接口。本项目代码是用 Python **独立实现**的，没有复制它的源码 |
| [CharlesPikachu/musicdl](https://github.com/CharlesPikachu/musicdl)、UnblockNeteaseMusic | — | 据 bobo-source 说明，波点签名算法最早来自这些项目的逆向，在此一并致谢 |
| [requests](https://github.com/psf/requests) | Apache-2.0 | HTTP 请求 |
| [python-qrcode](https://github.com/lincolnloop/python-qrcode) | BSD | 生成登录二维码 |
| [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) | Apache-2.0 | 繁简转换（让繁体歌名也能匹配） |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 / BSD | macOS 下解密 Chrome Cookie |

Apple Music 开发者令牌取自 music.apple.com 网页版前端，Chrome Cookie 解密是社区里通用的做法（同 pycookiecheat 等工具）。

## 开源协议

[MIT](LICENSE)
