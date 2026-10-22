# 踩坑记录

下面每一条都是实际碰到过的问题，按踩到的顺序排列。

## Apple Music 侧

### 1. amp-api 按「用户令牌」限流，不是按 IP

第一次定时运行就全部失败：目录搜索一半以上返回 `429 Too Many Requests`，代码重试几次后放弃，当天的歌单没建出来。

排查过程走了不少弯路，先后怀疑过 IP、DNS、代理，最后用对照实验才确认：

| 条件 | 20 次搜索中 429 的次数 |
|---|---|
| 直连，带 `Media-User-Token` | 6 / 8 / 12（测了三轮） |
| 直连，不带 `Media-User-Token` | 0 / 0 |
| 美国住宅代理，带令牌 | 0 |

**结论**：目录搜索（`/v1/catalog/{sf}/search`）本来就不需要用户身份，不要带 `Media-User-Token`。只有资料库读写（建歌单、加歌、删除）才带，这类操作每天只有几次。代码里用了两个 session 来区分。

额外的保险措施：
- 遇到 429 或 5xx 时按 5、10、20、40、60 秒指数退避。
- 匹配结果写入缓存，同一首歌以后不再重复搜。
- 单首歌搜索失败只跳过这一首，不影响整个歌单。
- 主任务之后安排两次 `--if-missing` 补跑。

### 2. 排查限流要做对照组，样本要够大

有一次对比 8 个请求，「走代理全部成功、直连有 3 个 429」，看起来是 IP 的问题。但把样本加到 20 次，并且交替跑对照组之后，发现两者完全一样，之前的结果只是碰巧。**样本至少 20 次，并且要交替测试。**

### 3. 别用代理软件的「规则分流」入口

Clash/mihomo 的通用端口（比如 7890）是按规则分流的。`amp-api.music.apple.com` 解析到 Apple 的国内节点，会命中 `GEOIP,CN` 或 `cncidr` 之类的规则，结果是 DIRECT 直连，相当于没走代理。

需要固定出口时，用配置里写死了 `proxy:` 的 listener，或者直接用住宅代理。如果机器在国内，住宅代理要**经过境外中转做链式代理**，直连境外节点又慢又可能被墙。

### 4. iTunes Search API 搜不到中国区

`itunes.apple.com/search?country=cn` 返回 `resultCount: 0`，中国区被禁用了。港区、台区能搜到，trackId 在全球通用，但结果是繁体，需要用 OpenCC 转成简体再比对。

**最后的方案**：直接用 amp-api 的 `/v1/catalog/cn/search`，返回的是简体中文，查的也正好是账号所在区域的曲库，查得到就能播放。

### 5. 开发者令牌每次现取

music.apple.com 前端的 `index~xxxx.js` 里内置了一个 JWT，有效期几个月。抓页面时**必须带浏览器 UA**，否则拿到的是空页面。脚本每次运行都会重新抓，不用担心过期。

### 6. 播放列表的几种行为

- 空播放列表的 `/tracks` 接口返回 **404**，不是空数组。
- 清空播放列表时要逐首调用 `DELETE /v1/me/library/playlists/{id}/tracks?ids[library-songs]=<id>&mode=all`。
- `DELETE /v1/me/library/playlists/{id}` 可以删除整个歌单（官方公开 API 不支持，网页版接口可以）。
- 歌只会加进播放列表，**不会**进「资料库 → 歌曲」，所以每天建歌单不会把资料库弄乱。
- 手机上歌单的排序由用户在 App 里选择。想让今天的排在最前面，选「最近添加」。

### 7. 从 Chrome 读 cookie

- Chrome 开着时 Cookies 库是锁住的，用 `sqlite3` 的 `?immutable=1` 只读方式打开。
- 解密密钥在钥匙串的「Chrome Safe Storage」里，读取时会弹窗，要点「允许」。
- **新版 Chrome（meta.version ≥ 24）在明文前加了 32 字节的域名哈希**，解密后要去掉。
- 浏览器自动化工具（比如用 `--profile` 启动的 agent-browser）往往用的是 profile 的副本，读不到用户刚登录的 cookie。直接读 Cookies 库更可靠。

## 波点侧

### 8. 只对大陆开放

用海外 IP 打开 App 会提示「由于版本保护，只对中国大陆开放」，没法听歌。同步脚本建议在国内网络下运行。接口在海外 IP 下是不是同样受限，没有系统验证过。

### 9. 签名的细节

- `urlencode` 必须是 Python `quote_plus` 的语义。如果自己用 JS 实现，`encodeURIComponent` 会漏掉 `! * ' ( )`。
- body 必须是紧凑 JSON（`separators=(",", ":")`、`ensure_ascii=False`），而且要和实际发送的字节完全一致。
- 缺少 `devid` 或 `qimei36` 请求头会返回 402。

### 10. 扫码登录

- 二维码内容是 `https://bodian-oia.kuwo.cn/bodian/download.html?pageName=login_pc&pt=3&id=<qrCode>`。
- 轮询状态：1 = 未扫，2 = 已扫待确认，3 = 已确认。
- 换取登录凭证的接口 `POST /api/ucenter/users/login` **也要签名**，返回的用户 ID 字段是 **`data.id`，不是 `uid`**。这里写错过一次，导致用户白扫了一次码。

### 11. 推荐不是「日更」

`home/module?moduleId=10/3` **每次请求都返回新的一批**，连续请求两次结果也不一样，相当于 App 里每次下拉刷新都换一批。所以几点去拉都可以，没有固定的更新时间。私人 FM 每轮要换一个 `lastColdStartTime`，否则会反复返回同一批。

### 12. 匹配率

实测稳定在 65%～80%。匹配不上的主要是：
- 翻唱，比如「xxx (cover: 某某)」
- 抖音网络歌、DJ 版
- 少数小众歌手

另外，`(Live)` 这类后缀会被去掉再比较，所以 Live 版可能匹配到录音室版。

## 运维

### 13. `pkill -f` 会杀掉自己

通过 ssh 执行 `pkill -f "python sync.py"` 时，ssh 起的 bash 命令行里也包含这串字，会把自己一起杀掉。写成 `pkill -f "[.]venv/bin/python sync.py"`，或者直接 kill PID。

### 14. macOS 没有 flock

`b2am.py cron` 会自动检测，没有 `flock` 时生成不带锁的配置。macOS 上可以 `brew install flock`。

### 15. `requests` 会读环境变量里的代理

机器上设置了 `http_proxy` 时，连波点也会走代理。代码里统一设置了 `trust_env = False`，只用显式配置的 `apple_proxy`。
