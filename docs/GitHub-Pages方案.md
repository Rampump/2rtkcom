# 2RTK.com · GitHub Pages 零服务器托管方案

> 用 GitHub Pages 免费托管首页 + 地图站，最大限度省服务器成本。
> 核心结论：静态部分全部免费，只有「采集器 + NTRIP Caster」需要一台最小服务器（或暂时用手动上传）。

---

## 一、GitHub Pages 能做什么 / 不能做什么

| 能力 | GitHub Pages | 你的需求 | 结论 |
|------|-------------|---------|------|
| 静态站托管 | ✅ 免费、无限流量 | 首页、地图站 | ✅ 完美 |
| 自定义域名 + HTTPS | ✅ 免费自动证书 | 2rtk.com / map.2rtk.com | ✅ 完美 |
| 跑 Python 采集 | ❌ 不支持 | lary.py | ❌ 需服务器 |
| 跑 NTRIP Caster | ❌ 不支持 | ntrtp caster | ❌ 需服务器 |

**一句话**：GitHub Pages 托管「展示层」，采集和 caster 属于「服务层」，必须另想办法。

---

## 二、三种数据同步方案（关键决策）

地图站的数据来自 `lary.py` 采集，采集必须在能联网+定时的地方跑。三种做法：

### 方案 A：定时 git push（推荐，最省）
- 采集器跑在**最小服务器**上（或你的电脑）
- 每 6 小时采集完，自动 `git push` 到 GitHub 仓库
- GitHub Pages 自动重新构建发布，地图数据自动更新

```
服务器/电脑: lary.py 采集 → data/*.json → git commit + push
                                          ↓
                              GitHub 仓库 (Pages 源)
                                          ↓
                          map.2rtk.com 自动更新
```

### 方案 B：对象存储 OSS
- 采集完上传 `data/*.json` 到 OSS（如腾讯云 COS / 阿里云 OSS）
- 地图页 `index.html` 改成从 OSS 读数据（跨域需配置）
- 优点：不依赖 GitHub；缺点：OSS 有费用、要配跨域

### 方案 C：地图站也放服务器（最简）
- 首页放 GitHub Pages（免费）
- 地图站 + 采集 + caster 都放一台服务器
- 优点：最简单；缺点：地图站没吃到 Pages 免费流量

**推荐方案 A**：既有 Pages 的免费，又自动化，只需一台最便宜服务器跑 caster + 采集。

---

## 三、完整架构（方案 A）

```
┌─────────────────────────────────────────────┐
│  GitHub Pages（免费，无需服务器）            │
├──────────────────┬──────────────────────────┤
│  2rtk.com        │  map.2rtk.com            │
│  首页 VitePress  │  地图 Cesium 页面         │
│  (仓库A)         │  (仓库B)                 │
└──────────────────┴──────────────────────────┘
         ↑ 自定义域名              ↑ 数据自动更新

┌─────────────────────────────────────────────┐
│  最小服务器（1核1G，最便宜）                 │
├─────────────────────────────────────────────┤
│  NTRIP Caster（2101 数据流 / 5757 管理）     │
│  lary.py 采集器（crontab 每 6 小时）         │
│  git push 自动同步 data/*.json 到仓库B      │
└─────────────────────────────────────────────┘
```

---

## 四、部署步骤

### 4.1 创建 GitHub 仓库
1. 建两个仓库：
   - `2rtk-site`（首页，VitePress 构建产物）
   - `2rtk-map`（地图站，index.html + data + images）
2. 都设为 **Public**（免费账号 Pages 只能 Public）

### 4.2 配置 GitHub Pages
1. 仓库 → Settings → Pages
2. Source 选 `main` 分支，根目录（或 `/docs`）
3. 保存后会给出一个 `username.github.io/仓库名` 的地址

### 4.3 绑定自定义域名
1. Pages 设置里 Custom domain 填 `2rtk.com` / `map.2rtk.com`
2. DNS 添加 CNAME 记录（见下表）
3. 勾选 Enforce HTTPS，GitHub 自动签发免费证书

### 4.4 DNS 配置
| 记录 | 类型 | 值 |
|------|------|-----|
| `2rtk.com` | CNAME | `你的用户名.github.io` |
| `map.2rtk.com` | CNAME | `你的用户名.github.io` |
| `caster.2rtk.com` | A | 服务器的 IP |

> 注意：GitHub Pages 用 CNAME，不是 A 记录。

### 4.5 上传首页（VitePress）
```bash
# 本地构建后，把产物推送到 2rtk-site 仓库
cd docs/.vitepress/dist
git init
git add .
git commit -m "deploy"
git remote add origin https://github.com/你的用户名/2rtk-site.git
git push -u origin main
```

### 4.6 上传地图站
```bash
# 把 index.html + data/ + images/ 推送到 2rtk-map 仓库
cd E:/2rtkcom
git init
git add index.html data images
git commit -m "init map"
git remote add origin https://github.com/你的用户名/2rtk-map.git
git push -u origin main
```

### 4.7 采集器自动同步（在服务器上）
```bash
# crontab 每 6 小时：采集 + 推送
0 */6 * * * cd /var/www/2rtk/map && python3 scheduler.py --once && git add data/ && git commit -m "update data $(date +%F_%T)" && git push >> /var/log/2rtk_sync.log 2>&1
```

---

## 五、GitHub Pages 的限制（必须知道）

| 限制 | 说明 | 对你的影响 |
|------|------|-----------|
| 仓库大小 | 建议 < 1GB | 你的 data 目录目前 <10MB，没问题 |
| 单文件 | < 100MB | 无影响 |
| 构建频率 | 免费版有限制 | 6 小时一次，完全够 |
| 只能静态 | 不能跑 Python/PHP | 采集必须另想办法 |
| 访问速度 | 国内访问 GitHub 可能慢 | 可考虑 Cloudflare CDN 加速 |

---

## 六、国内访问加速（可选）

GitHub Pages 在国内访问不稳定，两个方案：
1. **Cloudflare**：域名走 Cloudflare CDN，免费，全球加速
2. **国内 CDN**（如又拍云/七牛）：需备案，速度更快

如果你主要面向国内用户，建议**首页 + 地图用国内 CDN 或直接放国内服务器**，GitHub Pages 做备份源。

---

## 七、成本对比

| 方案 | 服务器 | 托管 | 总成本/月 |
|------|--------|------|-----------|
| 纯 GitHub Pages + 最省服务器 | 1核1G（跑 caster） | 免费 | ~¥30-50 |
| 全放服务器 | 2核2G | 自建 | ~¥60-100 |
| GitHub Pages + 国内 CDN | 1核1G | CDN 按流量 | ~¥50-80 |

**结论**：GitHub Pages 方案能省一半成本，前提是能接受「采集仍需一台服务器」这个事实。

---

## 八、待你确认的事

1. **NTRIP Caster 是否已有服务器？** 如果没有，反正要买一台跑 caster，那把采集也放上去，几乎零额外成本。
2. **面向国内还是海外用户？** 决定是否要用国内 CDN。
3. **数据同步选哪种**：方案 A（git push）/ B（OSS）/ C（地图也放服务器）？

告诉我这几点，我帮你把方案落到可执行的具体步骤（包括实际的 git 命令和 Pages 配置）。
