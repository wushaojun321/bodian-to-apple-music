# 接口说明

都是非官方接口，下面记录的是 2026 年 10 月实测可用的状态。

## 波点 bd-api（`https://bd-api.kuwo.cn`）

**通用请求头**（伪装 Windows 客户端）：

```
user-agent: Dart/3.3 (dart:io)
plat: win          channel: W1        ver: 1.1.5      svrver: 13
api-ver: application/json             content-type: application/json
brand: Windows 11 Pro for Workstations                net: wifi
devid: <32 位 hex，自己随机生成并固定>    qimei36: <同 devid>
```

**签名**：每个请求都加上 `timestamp`（毫秒），再加 `sign`：

```
seed = "kuwotest" + sorted(urlencode(params) 中的 [A-Za-z0-9] 字符)
若有 body: seed += md5(body + "kuwotest")
sign = md5(seed + path)
```

| 用途 | 请求 | 参数 / 说明 |
|---|---|---|
| 取登录码 | `GET /api/ucenter/login/qrCode` | `uid=-1&token=` → `data.qrCode` |
| 轮询扫码状态 | `GET /api/ucenter/login/qrCodeStatus` | `qrCode`，`uid=-1` → `data.status`（3 表示已确认） |
| 换取凭证 | `POST /api/ucenter/users/login` | body `{"authType":10,"qrCode":...}` → `data.id` / `data.token` / `data.userInfo.nickname` |
| 首页模块目录 | `GET /api/service/home/index` | → `data.moduleList[] {id,type,name}` |
| 某个首页模块 | `GET /api/service/home/module` | `moduleId`：10 心动收藏相似推荐，3 偶遇心动单曲 → `data.musicList` |
| 私人 FM | `GET /api/service/music/recommendList` | `fg=1&lock=0&recoMode=normal&scrollNum&totalNum&lastColdStartTime` → `data.musicList` |

除了登录相关的接口，其它请求都要带上 `uid` 和 `token`。歌曲字段：`id`、`name`、`artist`（多个歌手用 & 连接）、`album`、`duration`（秒）。

## Apple Music amp-api（`https://amp-api.music.apple.com`）

请求头：`Authorization: Bearer <开发者令牌>`、`Origin: https://music.apple.com`；资料库相关接口再加 `Media-User-Token`。

| 用途 | 请求 | 是否带用户令牌 |
|---|---|---|
| 账号区域 | `GET /v1/me/storefront` | 带 |
| 目录搜索 | `GET /v1/catalog/{sf}/search?term=&types=songs&limit=10` | **不带**（带了会被限流） |
| 列出资料库歌单 | `GET /v1/me/library/playlists?limit=100`（按 `next` 翻页） | 带 |
| 建歌单 | `POST /v1/me/library/playlists`，body 里带 attributes 和 relationships.tracks | 带 |
| 往歌单里加歌 | `POST /v1/me/library/playlists/{id}/tracks` | 带 |
| 列出歌单曲目 | `GET /v1/me/library/playlists/{id}/tracks`（空歌单返回 404） | 带 |
| 从歌单删歌 | `DELETE /v1/me/library/playlists/{id}/tracks?ids[library-songs]=<id>&mode=all` | 带 |
| 删除歌单 | `DELETE /v1/me/library/playlists/{id}` | 带 |
