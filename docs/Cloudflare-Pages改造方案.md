# Cloudflare Pages 改造方案（含 GitHub 自动采集）

> 目标：把现有 Cesium 地图站改造为可在 Cloudflare Pages 免费托管，并由 GitHub Actions 每 6 小时自动采集数据回提交。
>
> 改造已完成并本地验证通过。

---

## 一、改造总览

| 项目 | 改造前 | 改造后 |
|------|--------|--------|
| Cesium 加载 | `cesium.com` 源站（实测 20s） | jsDelivr CDN 固定版本 `1.107` |
| 静态资源基址 | 未声明（源站相对路径可用） | `CESIUM_BASE_URL` 显式指向 CDN |
| Ion Token | 硬编码在 HTML | 构建时注入 `config.js`，不入库 |
| 底图降级 | 无 | Ion → 天地图 → 纯色椭球（三级） |
| `files.json` | 手工维护，易漏 | 构建脚本扫描 `data/` 自动生成 |
| 数据采集 | 本地/服务器 scheduler.py | GitHub Actions cron，每 6 小时 |
| 部署产物 | 仓库根目录直接托管 | `dist/` 构建产物 |

---

## 二、三个必须知道的坑（都踩过并已解决）

### 坑 1：`CESIUM_BASE_URL` 漏配 → Workers/Assets 全 404

Cesium 运行时需要动态加载 `Workers/`、`Assets/`、`ThirdParty/`。一旦 Cesium.js 来自 CDN 而非同目录，必须显式声明基址，否则地形、影像、Worker 全部失效，页面表现为白屏或黑球。

```html
<script>window.CESIUM_BASE_URL = 'https://cdn.jsdelivr.net/npm/cesium@1.107/Build/Cesium/';</script>
<script src="https://cdn.jsdelivr.net/npm/cesium@1.107/Build/Cesium/Cesium.js"></script>
```

### 坑 2：Cesium 1.107 下用 `baseLayer` 会抛跨域错误并卡死页面

`baseLayer: new Cesium.ImageryLayer(...)` 是 1.104+ 的新写法，但在 1.107 配合 CDN 时会抛 `Script error.`（跨域脚本错误，无详细信息），导致后续所有初始化中断——按钮只渲染一半、数据不加载。

**必须用 1.107 的 `imageryProvider` 参数**：

```js
viewerOptions.imageryProvider = new Cesium.IonImageryProvider({ assetId: 2 });
```

### 坑 3：底图不能用 OSM / 高德

- `tile.openstreetmap.org`、`services.arcgisonline.com`：国内实测**完全不可达**（连接超时），会导致黑球
- 高德/腾讯瓦片：国内可达，但使用 **GCJ-02 火星坐标**，与 RTK 站点使用的 WGS84 偏差数百米 —— 对厘米级定位展示是灾难性错误

正确的国内可用、坐标兼容底图是**天地图**（CGCS2000，与 WGS84 差异在厘米级）。

---

## 三、改造后的代码结构

```
2rtkcom/
├── index.html                  # 地图站主页面（已改造）
├── lary.py                     # 采集器（支持 NTRIP_CONFIG 环境变量）
├── scheduler.py                # 本地/服务器定时调度（Pages 部署后不再需要）
├── ntrip_servers.ini           # 私有配置（含凭据，不入库）
├── ntrip_servers.ci.ini        # CI 用公开源配置（入库）
├── config.js                   # 构建生成的运行时配置（不入库）
├── scripts/
│   └── build.py                # 构建脚本
├── .github/workflows/
│   └── collect.yml             # 定时采集工作流
├── data/                       # 采集数据（入库，随 Actions 更新）
├── images/                     # 卫星国旗图标
└── dist/                       # 构建产物（不入库）
```

### 前端底图三级降级逻辑

```js
const HAS_ION = ION_TOKEN.length > 20;

if (HAS_ION) {
  viewerOptions.imageryProvider = new Cesium.IonImageryProvider({ assetId: 2 });
} else if (TIANDITU_KEY) {
  viewerOptions.imageryProvider = new Cesium.WebMapTileServiceImageryProvider({ /* 天地图 */ });
  viewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
} else {
  viewerOptions.imageryProvider = false;              // 纯色球，站点坐标仍准确
  viewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
}
```

无底图时 `baseLayerPicker` 与 `geocoder` 自动关闭（其内置图层依赖 Ion）。

### 构建脚本做了什么

```bash
python scripts/build.py              # 完整构建到 dist/
python scripts/build.py --files-json # 仅刷新 data/files.json（Actions 用）
```

1. 扫描 `data/*.json`，逐个校验 JSON 合法性（坏文件不进列表），生成 `data/files.json`
2. `data/2rtk.json` 缺失时生成 `[]` 占位，避免前端按钮 404
3. 复制 `index.html`（替换 `__BUILD_ID__` 为时间戳，避免 config.js 缓存）、`images/`、`data/*.json` 到 `dist/`
4. 由环境变量生成 `dist/config.js`：

```js
window.__2RTK_CONFIG = { "cesiumIonToken": "...", "tiandituToken": "..." };
```

---

## 四、Cloudflare Pages 配置

### 4.1 创建项目

Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git → 选仓库。

### 4.2 构建设置

| 配置项 | 值 |
|--------|-----|
| Production branch | `main` |
| Framework preset | None |
| Build command | `python3 scripts/build.py` |
| Build output directory | `dist` |

### 4.3 环境变量（Settings → Environment variables）

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `CESIUM_ION_TOKEN` | 你的 Ion Token | 不填则降级到天地图/纯色球 |
| `TIANDITU_TOKEN` | 天地图 key（可选） | [申请地址](https://console.tianditu.gov.cn/api/key)，个人免费 |

> 两者都配置时优先 Ion。环境变量只在构建期使用，不会出现在客户端代码里——除了被写进 `config.js` 的那一个，这是静态站无法避免的。

### 4.4 绑定域名

Custom domains → 添加 `map.2rtk.com`（域名 NS 需已托管到 Cloudflare）。

---

## 五、GitHub Actions 自动采集

### 5.1 工作流逻辑（`.github/workflows/collect.yml`）

```
每 6 小时（cron: 0 */6 * * *）+ 支持手动触发
  ↓
checkout → setup-python 3.11 → pip install requests
  ↓
cp ntrip_servers.ci.ini ntrip_servers.ini
  ↓（若配置了 secrets，追加私有 caster 段）
python lary.py    （NTRIP_CONFIG=ntrip_servers.ini）
  ↓
python scripts/build.py --files-json   刷新 files.json
  ↓
git commit data/ && git push          触发 Pages 自动重建
```

### 5.2 私有 caster（自建 2rtk.com:2101）接入

在仓库 Settings → Secrets and variables → Actions 添加：

| Secret | 示例值 |
|--------|--------|
| `NTRIP_2RTK_HOST` | `你的服务器公网IP` |
| `NTRIP_2RTK_PORT` | `2101` |
| `NTRIP_2RTK_USERNAME` | 你的 caster 账号 |
| `NTRIP_2RTK_PASSWORD` | 你的 caster 密码 |

配置后工作流会自动追加 `[2rtk]` 段并生成 `data/2rtk.json`。未配置则跳过，不影响其他源。

> 注意：GitHub Actions 的 runner 在境外，若你的 caster 在国内且只监听内网/防火墙限制境外 IP，将采集失败。此时应改为把数据文件直接从服务器 `git push`。

### 5.3 定时任务的两个已知特性

- **会延迟**：GitHub 的 cron 在高峰期可能延迟数分钟到数十分钟，不适合精确到分钟的场景
- **会休眠**：仓库连续 60 天无提交活动，schedule 会被自动停用。本工作流每 6 小时回提交数据，天然保活

---

## 六、Ion Token 安全（重要）

### 6.1 当前状态

Token 已从 `index.html` 移除，改由环境变量注入。但**旧 token 已存在于 Git 历史中**（首次提交时硬编码）。

### 6.2 必须做的两件事

**① 轮换 Token**（因为旧 token 已泄露在历史里）

Cesium Ion → Access Tokens → 删除旧 token → 新建 → 更新到 Cloudflare Pages 环境变量。

**② 设置域名白名单**

Cesium Ion → Access Tokens → 编辑 → Allowed URLs 填入：

```
map.2rtk.com
localhost
```

设置后即使 token 泄露，也只能在你指定的域名下使用，别人盗用无效。

> 静态站无法真正隐藏 token——浏览器一定会拿到它。域名白名单是唯一有效的防护手段。

---

## 七、验证清单

本地已验证通过：

```bash
# 1. 构建
python scripts/build.py
# → data/files.json 27 项，dist/ 生成

# 2. 本地预览
cd dist && python -m http.server 8092
# 打开 http://127.0.0.1:8092/index.html

# 3. CI 配置解析
NTRIP_CONFIG=ntrip_servers.ci.ini python -c "import lary; print(len(lary.load_config()))"
# → 29

# 4. 端到端采集
NTRIP_CONFIG=ntrip_servers.ci.ini python -c "
import lary
s=[x for x in lary.load_config() if x['name']=='HongKong'][0]
print(lary.fetch_mountpoints(s))"
# → (True, '成功处理 5 个挂载点')
```

实测结果（有 Ion Token）：Bing 影像正常、826 个 rtk2go 站点渲染、168 颗 GNSS 卫星带国旗图标、数据更新时间正常显示。

实测结果（无任何 Token）：纯色椭球 + 站点橙色覆盖圈 + 卫星，页面无报错。

---

## 八、上线步骤

1. 轮换 Ion Token 并设置域名白名单
2. GitHub 建私有仓库，推送代码
3. Cloudflare Pages 连接仓库，配置 build command / output dir / 环境变量
4. 绑定 `map.2rtk.com`
5. 手动触发一次 Actions（Actions → Collect NTRIP Data → Run workflow），确认数据回提交、Pages 自动重建
6. 访问 `https://map.2rtk.com` 验收

---

## 九、成本

| 项目 | 费用 |
|------|------|
| Cloudflare Pages | ¥0（无限流量） |
| GitHub Actions（公开仓库） | ¥0 |
| GitHub Actions（私有仓库） | 2000 分钟/月免费，本工作流约用 30 分钟/月 |
| Cesium Ion | 免费额度内（个人学习用途） |
| **合计** | **¥0** |
