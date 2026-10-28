# 2RTK.com · Cloudflare Pages 零服务器托管方案

> 用 Cloudflare Pages 免费托管首页 + 地图站，无限流量、自动构建、国内访问更友好。
> 同样：静态部分全免费，只有「采集器 + NTRIP Caster」需要一台最小服务器。

---

## 一、为什么 Cloudflare Pages 比 GitHub Pages 更适合你

| 维度 | GitHub Pages | Cloudflare Pages |
|------|-------------|-----------------|
| 免费流量 | 100GB/月 | **无限** |
| 自动构建 | 需自己配 Action | **git push 自动构建部署** |
| 国内访问 | 慢、不稳定 | **较稳定** |
| VitePress 支持 | 手动构建上传 | **原生自动 npm build** |
| 自定义域名+HTTPS | 支持 | 支持（自动） |
| 构建额度 | 有限 | 500 次/月（够用） |

**核心优势**：Cloudflare Pages 直接连你的 GitHub 仓库，每次 `git push` 自动构建部署，不用手动 `npm run build` + 上传。

---

## 二、架构（和 GitHub Pages 版基本一致）

```
┌─────────────────────────────────────────────┐
│  Cloudflare Pages（免费，无需服务器）        │
├──────────────────┬──────────────────────────┤
│  2rtk.com        │  map.2rtk.com            │
│  首页 VitePress  │  地图 Cesium 页面         │
│  (项目A)         │  (项目B)                 │
└──────────────────┴──────────────────────────┘
         ↑ 自动构建部署            ↑ 数据自动更新

┌─────────────────────────────────────────────┐
│  最小服务器（跑 caster + 采集）              │
│  NTRIP Caster（2101 / 5757）                │
│  lary.py 采集器（crontab 6h）               │
│  git push 同步 data/*.json                  │
└─────────────────────────────────────────────┘
```

---

## 三、部署步骤

### 3.1 准备 GitHub 仓库（Cloudflare 依赖它）
Cloudflare Pages 从 GitHub 仓库拉源码构建。建两个仓库：
- `2rtk-site`（首页 VitePress 源码，含 package.json）
- `2rtk-map`（地图站源码）

### 3.2 首页项目配置（VitePress）
在 `2rtk-site` 仓库根目录放好：
```
package.json
docs/
├── .vitepress/
└── index.md 等教程
```

构建命令配置（Cloudflare 里填）：
- **Build command**: `npm run docs:build`
- **Output directory**: `docs/.vitepress/dist`

### 3.3 创建 Cloudflare Pages 项目
1. 登录 Cloudflare → Workers & Pages → Create → Pages
2. 连接 GitHub，选 `2rtk-site` 仓库
3. 填构建命令和输出目录（见上）
4. 部署

### 3.4 地图站项目
地图站是纯静态（无构建），配置：
- **Build command**: 留空
- **Output directory**: `/`（根目录）

### 3.5 绑定自定义域名
1. Pages 项目 → Custom domains → Add
2. 填 `2rtk.com` / `map.2rtk.com`
3. Cloudflare 自动签发 HTTPS 证书

### 3.6 DNS 配置
把域名托管到 Cloudflare（改 NS 到 Cloudflare），然后：
| 记录 | 类型 | 值 |
|------|------|-----|
| `2rtk.com` | CNAME | `你的项目.pages.dev` |
| `map.2rtk.com` | CNAME | `你的项目.pages.dev` |
| `caster.2rtk.com` | A | 服务器 IP |

---

## 四、数据自动更新（关键）

地图站数据来自采集，同步方式和 GitHub Pages 方案一样，三种选择：

### 方案 A：定时 git push（推荐）
```bash
# 服务器 crontab，每 6 小时
0 */6 * * * cd /var/www/2rtk/map && python3 scheduler.py --once && git add data/ && git commit -m "update $(date +%F_%T)" && git push
```
Cloudflare Pages 检测到 push 自动重新构建部署，数据自动更新。

### 方案 B：Cloudflare R2（对象存储）
- Cloudflare 自家的对象存储，免费 10GB
- 采集完用 `rclone` 或 API 上传 data/*.json 到 R2
- 地图页从 R2 读数据

### 方案 C：地图也放服务器（最简）

---

## 五、Cloudflare 的额外免费福利

| 功能 | 说明 |
|------|------|
| CDN 加速 | 全球节点，国内访问快 |
| DDoS 防护 | 免费 |
| SSL 证书 | 自动免费 |
| Workers（边缘函数） | 可做简单的动态逻辑 |
| R2 存储 | 10GB 免费对象存储 |

---

## 六、限制与注意事项

| 限制 | 说明 |
|------|------|
| 单文件大小 | 25MB（Cloudflare Pages） |
| 构建时间 | 每次 < 20 分钟 |
| 构建次数 | 500 次/月（超出收费，但 6 小时一次=120次/月，够用） |
| 免费版 | 不能跑持续运行的服务端程序 |

---

## 七、成本对比（三方案）

| 方案 | 托管 | 服务器 | 月成本 |
|------|------|--------|--------|
| Cloudflare Pages | 免费无限流量 | 1核1G（caster） | ~¥30-50 |
| GitHub Pages | 免费 100GB | 1核1G（caster） | ~¥30-50 |
| 全服务器 | 自建 | 2核2G | ~¥60-100 |

**推荐 Cloudflare Pages**：无限流量 + 国内访问好 + 自动构建，性价比最高。

---

## 八、待你确认

1. **NTRIP Caster 是否已有服务器？**（采集可顺带放上去）
2. **面向国内用户？** Cloudflare Pages 已经比 GitHub Pages 好，但纯国内极致体验还需备案 + 国内 CDN
3. **数据同步选哪种**：A（git push）/ B（R2）/ C（地图也放服务器）
