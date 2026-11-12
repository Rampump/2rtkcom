# 从零上线：GitHub + Cloudflare Pages 完整教程

> 适用对象：本地已有 `E:\2rtkcom` 这个仓库，但 GitHub 还没建仓库、Cloudflare 还没建项目。
> 全程约 40 分钟，绝大部分时间在等 GitHub Actions 跑和等 Cloudflare 首次部署。

---

## 0. 先说清楚：整个架构长什么样

```
你的电脑                       GitHub                           Cloudflare Pages
─────────                     ──────                           ────────────────
写内容 / 改页面
  │
  ├─ git push ───────────────► 仓库 main 分支
  │                               │
  │                               ├─ 有代码改动 ──► Cloudflare 构建 ──► 发布上线
  │                               │                  (sh scripts/cf-build.sh)
  │                               │
  │                               └─ Actions 每 6 小时
  │                                  抓 CRTK / RTK2GO / IGS / TLE
  │                                  提交 data/ ────────────────────► 触发构建 ──► 发布
  │
  └─ 不需要上传 dist/
```

**一句话分工**：

- **GitHub 只存源码**（HTML、CSS、JS、Python 脚本、data/*.json），**不存构建产物 `dist/`**
- **Cloudflare 负责构建和托管**，每次收到 GitHub 推送就自动跑 `sh scripts/cf-build.sh`，把 `dist/` 发布成网站
- 站点是**纯静态**的，没有后端 API、没有数据库，前端直接读同域的 `./data/*.json`

---

## 1. 哪些文件进 GitHub，哪些不进

### 1.1 必须进 GitHub（构建需要 / 网站内容）

| 路径 | 说明 | 体积 |
|---|---|---|
| `index.html` | 地图首页（Cesium 地图 + 站点 + 卫星） | 68 KB |
| `site/` | 5 个内容页源码：`rtk-base/` `caster/` `what-is-rtk/` `test-caster/` `about/` | 312 KB |
| `site/assets/` | 全站共用 CSS / JS | 内含 |
| `site/_redirects` | **Cloudflare 专用**：旧链接 301 跳转规则，必须放在仓库里，构建时被复制到 `dist/` 根 | 1 KB |
| `site/_headers` | **Cloudflare 专用**：安全响应头 + 缓存策略，同上 | 1 KB |
| `images/` | 教程截图、国旗图标 | ~3 MB |
| `scripts/` | `build.py`（构建）、`fetch_tle.py`（卫星）、`summarize.py`（采集摘要）、`shoot_base.py`（截图工具） | 小 |
| `lary.py` | NTRIP 采集主脚本 | 小 |
| `ntrip_servers.ci.ini` | **CI 专用配置**：只含 rtk2go / crtk 两个公开源，无账号密码 | 小 |
| `scheduler.py` | 本地定时器（可选，用于在自己机器上跑采集） | 小 |
| `data/*.json` | 站点数据：`rtk2go.json` `France.json`(CRTK) `IGSNetwork.json` `2rtk.json` `files.json` `meta.json` | ~2.8 MB |
| `data/tle-gnss.txt` | 卫星 TLE，前端直接读，**必须入库**（否则每人都去拉 CelesTrak 会被限流） | 26 KB |
| `.github/workflows/collect.yml` | 每 6 小时自动采集的工作流 | 小 |
| `.python-version` | 内容就一行 `3.11`，告诉 Cloudflare 用哪个 Python | 6 字节 |
| `.gitignore` | 决定哪些不进仓库 | 小 |
| `docs/` | 方案文档，进不进都行，进了方便以后查 | 小 |

> `data/` 每轮采集都会变，仓库体积会缓慢增长。当前 4 个 JSON 约 2.8 MB，按每 6 小时一次、每次都有变化算，一年大约增加几十 MB——但**同一文件反复覆盖，Git 只存差异，实际增长远小于这个数**。真到几百 MB 时再考虑改用 Cloudflare R2 或缩短历史，现在不用管。

### 1.2 绝对不能进 GitHub（含密钥 / 是产物）

| 路径 | 原因 |
|---|---|
| `ntrip_servers.ini` | **含 2rtk.net 的 Caster 账号密码**。已被 `.gitignore` 排除，请勿强行添加 |
| `config.js` | 由构建生成，可能含 Cesium Ion Token。已被排除，改由 Cloudflare 环境变量注入 |
| `dist/` | 构建产物，13 MB。Cloudflare 自己会生成，传上去只会冲突 |
| `data/*.txt`（除 tle-gnss.txt） | 采集过程中的中间文本（`France.txt` `rtk2go.txt`），前端不读，`data/*.txt` 已被忽略，仅放行 `tle-gnss.txt` |
| `.workbuddy/` | 我的本地工作日志 |
| `.tmp/` | 临时文件（截图等） |
| `__pycache__/` `.venv/` | Python 运行时缓存 |

### 1.3 谁负责什么（易混淆点）

| 文件 | 放哪 | 为什么 |
|---|---|---|
| `_redirects` / `_headers` | 源文件在 `site/`，**由 `build.py` 复制到 `dist/` 根** | Cloudflare 只认**输出目录根**下的这两个文件，放 `site/` 里不生效 |
| `.python-version` | 仓库根目录 | Cloudflare 构建时在仓库根扫描这个文件决定 Python 版本 |
| `ntrip_servers.ini` | **两边都不放**（本地留一份自用） | CI 用 `.ci.ini` + Secrets 拼出来 |
| `2rtk.net` 的账号密码 | **GitHub Secrets** | 加密存储，日志里自动打码，不会出现在代码里 |

---

## 2. 第一步：在 GitHub 建仓库并推送

### 2.1 建仓库

1. 打开 https://github.com/new
2. **Repository name**：`2rtkcom`（随便取，后面 Cloudflare 要选这个）
3. **Description**：可留空
4. **Public / Private**：都行。
   - 选 **Public**：Actions 免费额度无限，Cloudflare 也能连私有仓库，但公共仓库最省事
   - 选 **Private**：Actions 每月 2000 分钟免费额度，每轮采集约 2~4 分钟、一天 4 轮 ≈ 每月 500 分钟，**够用**
5. **⚠️ 关键：下面的 "Initialize this repository" 三项全部不要勾**
   - 不要勾 `Add a README file`
   - 不要勾 `Add .gitignore`
   - 不要勾 `Choose a license`

   > 勾了会生成一个初始提交，和你本地的 4 次提交冲突，push 时会报 `rejected (fetch first)`。

6. 点 **Create repository**
7. 页面会显示一串命令。**先别急着复制**，因为你的分支叫 `main`，GitHub 给的示例可能叫 `master`，以本文为准。

### 2.2 在本地检查后推送

在 `E:\2rtkcom` 里执行（Git Bash 或 PowerShell 都行）：

```bash
cd /e/2rtkcom

# 1) 确认当前分支是 main
git branch --show-current
# 输出应该是 main

# 2) 确认敏感文件没被跟踪（应该是空的，或者只有 .ci.ini）
git ls-files | grep ntrip_servers

# 3) 确认待提交内容干净
git status --short
```

> 第 2 步如果列出了 `ntrip_servers.ini`，**立刻停止**，执行：
> `git rm --cached ntrip_servers.ini` 然后重新提交，否则密码会进公开历史。

然后关联远程仓库并推送（把 `你的用户名` 换成 GitHub 用户名）：

```bash
git remote add origin https://github.com/你的用户名/2rtkcom.git
git push -u origin main
```

### 2.3 认证方式（2021 年后不能用密码）

推送时会让你输账号密码，**密码位置要填 Personal Access Token，不是登录密码**：

1. 打开 https://github.com/settings/tokens?type=beta （Fine-grained token）或 https://github.com/settings/tokens （Classic）
2. Classic 更简单：**Generate new token (classic)** → Note 填 `2rtk-push` → Expiration 选 90 days → 勾选 **`repo`** 整组 → 底部 **Generate token**
3. **复制那串 `ghp_...`，只显示一次**
4. 回到终端：
   - Username：`你的GitHub用户名`
   - Password：粘贴 `ghp_...`

Windows 上会弹「Windows 凭据管理器」，选「Git Credential Manager」就会记住，下次不用再输。

> 也可以用 SSH：`git remote set-url origin git@github.com:你的用户名/2rtkcom.git`，前提是你本地已有 SSH key 并已加到 GitHub。新手建议先用 Token。

### 2.4 验证推送成功

刷新 GitHub 仓库页面，你应该看到：

- 文件列表里有 `index.html`、`site/`、`data/`、`scripts/`、`.github/`、`.python-version`
- **没有** `dist/`、`ntrip_servers.ini`、`config.js`
- 顶部提交数显示 4 次（或你本地的提交数）
- `data/` 目录里 `France.json` 等都在

---

## 3. 第二步：配置 GitHub Actions（数据自动采集）

仓库建好、代码推上去之后，`.github/workflows/collect.yml` 就已经生效了，但**先手动跑一次**看看有没有问题。

### 3.1 加 2rtk.net 的 Secrets（可选，等你 Caster 上线再做）

你说 2rtk.net 先不管，那**这一节可以直接跳过**。没配的话工作流会打一条 warning 并跳过这一路，其他三路照常跑。

将来要接的时候：仓库 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**，加四个：

| Name | Value 示例 |
|---|---|
| `NTRIP_2RTK_HOST` | `2rtk.net` |
| `NTRIP_2RTK_PORT` | `2101` |
| `NTRIP_2RTK_USERNAME` | 你的 caster 账号 |
| `NTRIP_2RTK_PASSWORD` | 你的 caster 密码 |

### 3.2 手动触发第一次采集

1. 仓库页顶部点 **Actions** 标签
2. 左侧列点 **Collect NTRIP Data**
3. 右侧有 **Run workflow** 下拉 → 分支选 `main` → 点绿色 **Run workflow**
4. 刷新页面，出现一条新的运行记录，点进去能看实时日志

**日志里重点看这几行：**

```
[✓ 成功] rtk2go: 成功处理 755 个挂载点
[✓ 成功] crtk: 成功处理 1328 个挂载点
[✓] IGS 坐标 ok
[✓] CelesTrak 169 颗卫星 → tle-gnss.txt 26.5 KB
```

结束时点运行记录顶部的 **Summary**，会看到一张表：每个源成功/失败、各多少站点、更新时间。

### 3.3 确认数据被提交了

回到仓库首页，应该看到一条新提交：

```
data: auto update 2026-11-11 11:05 UTC    github-actions[bot]
```

如果 Actions 报 `Permission denied` 或 `403`：
仓库 → **Settings** → **Actions** → **General** → 拉到最下面 **Workflow permissions** → 选 **Read and write permissions** → Save。然后再跑一次。

### 3.4 定时任务说明

- cron `0 */6 * * *` 是 **UTC 时间**，对应北京时间 **08:00 / 14:00 / 20:00 / 02:00**
- **重要：把仓库连续 60 天没有任何活动，GitHub 会自动停用定时任务**。你只要偶尔 push 一次代码就会重新激活；或者每两个月去 Actions 页面手动跑一次
- 定时任务不保证准点，高峰期可能延迟 5~20 分钟，这是 GitHub 的正常行为

---

## 4. 第三步：Cloudflare Pages 建项目

### 4.1 前提：把域名托管到 Cloudflare

因为最后要绑 `2rtk.com`，所以先把域名的 NS 指到 Cloudflare：

1. 登录 https://dash.cloudflare.com
2. 左上 **Add** → **Existing domain**（域名已经买了）
3. 输入 `2rtk.com` → 选 **Free** 套餐
4. Cloudflare 给你两个 NS，例如 `ada.ns.cloudflare.com`、`bob.ns.cloudflare.com`
5. 去你的域名注册商（阿里云 / 腾讯云 / Namecheap 等）后台，把 NS 改成这两个
6. 回 Cloudflare 点 **Check nameservers**，生效一般 10 分钟到 24 小时

> 只想先看效果、域名以后再说：跳到 4.2 直接建项目，Cloudflare 会给你一个 `xxx.pages.dev` 的免费域名，一样能访问。只是那时页面里的 canonical 和 sitemap 还写着 `https://2rtk.com`，搜索引擎会有点困惑，正式上线前务必绑好域名。

### 4.2 创建 Pages 项目

1. Cloudflare 控制台左侧 → **Workers & Pages** → **Create**
2. 选 **Pages** 标签 → **Connect to Git**
3. 第一次用要点 **Connect GitHub**，授权 Cloudflare 访问你的仓库
   - 建议选 **Only select repositories**，只勾 `2rtkcom`，别给全仓库权限
4. 选中 `2rtkcom` → **Begin setup**
5. 填构建配置（**这一页最容易填错，严格按下面来**）：

| 字段 | 填什么 | 说明 |
|---|---|---|
| **Project name** | `2rtkcom` | 会变成 `2rtkcom.pages.dev`，之后改不了 |
| **Production branch** | `main` | 必须和你 git 分支一致 |
| **Framework preset** | `None` | 不是 Next.js/Vite，选 None |
| **Build command** | `sh scripts/cf-build.sh` | 包装脚本会自动挑选可用的 Python 3，规避镜像里 `python` / `python3` 不一致的问题 |
| **Build output directory** | `dist` | 注意：不带斜杠，也不是 `site` |

6. 展开 **Environment variables (advanced)**，现在可以先不加，直接点 **Save and Deploy**

### 4.3 首次部署

点完 Save and Deploy 后，Cloudflare 开始构建，大约 1~3 分钟。日志里你会看到：

```
Cloning repository...
Repo root: /opt/buildhome/repo
Using interpreter: python3 (Python 3.11.x)
[ok] data/files.json 已更新，共 4 个数据文件
[ok] 已同步 data/tle-gnss.txt（26.5 KB）
[info] 未配置 Ion 凭证，将使用公共图源
[ok] 已复制 Cloudflare 配置 _headers
[ok] 已复制 Cloudflare 配置 _redirects
[ok] 内容页渲染完成，共 5 个 HTML 页面
[ok] 已生成 robots.txt 与 sitemap.xml（6 条 URL）
[ok] 构建完成 -> dist
Success: Your site was deployed!
```

成功后会给你一个地址，形如 `https://2rtkcom.pages.dev`。点开验证：

- 首页地图能加载，能看到站点和卫星
- 点进 `/about/` `/rtk-base/` `/caster/` `/what-is-rtk/` `/test-caster/` 都正常
- 访问 `/data/meta.json` 能看到 JSON

### 4.4 加 Cesium Ion Token（可选）

不加的话地图用公共图源（Esri 影像 / OSM），能用但影像分辨率一般。要加：

1. 去 https://ion.cesium.com/tokens 注册并新建一个 token（免费额度够个人站用）
2. Cloudflare Pages 项目 → **Settings** → **Environment variables** → **Add variable**
   - Variable name：`CESIUM_ION_TOKEN`
   - Value：你的 token
   - **Type 选 Secret**（加密，之后看不到值）
3. 加完去 **Deployments** → 最新一条右侧 **⋯** → **Retry deployment**，重新构建一次才生效

> 构建脚本优先读 `CESIUM_ION_TOKEN`，读到就写进 `dist/config.js`；`config.js` 本身永远不进仓库。

---

## 5. 第四步：绑定自定义域名

1. Pages 项目 → **Custom domains** → **Set up a custom domain**
2. 输入 `2rtk.com` → **Continue**
3. 因为 4.1 已经把 NS 托管到 Cloudflare，它会自动加一条 CNAME，**直接点 Activate domain**
4. 再加一次 `www.2rtk.com`，同样操作
5. 状态从 `Pending` 变 `Active` 通常几分钟；证书签发最多 24 小时

### 5.1 建议同时做的三件事

**① 强制 HTTPS**：域名页面（不是 Pages 页面）→ **SSL/TLS** → **Edge Certificates** → 打开 **Always Use HTTPS**

**② www 跳主域**：Pages 项目 → **Custom domains**，把 `www.2rtk.com` 设为 **Redirect** 到 `2rtk.com`（Pages 会让你选哪个是主域），比写 `_redirects` 更干净

**③ SEO 检查**：浏览器打开 `https://2rtk.com/robots.txt` 和 `https://2rtk.com/sitemap.xml`，确认里面的域名是 `https://2rtk.com` 而不是 `pages.dev`

---

## 6. 日常维护：你以后只做这两件事

### 6.1 改页面内容

```bash
cd /e/2rtkcom
# 改 site/xxx/index.html 或 index.html
python scripts/build.py      # 本地先构建，检查 dist/ 有没有问题
git add -A
git commit -m "改了什么"
git push
```

**push 之后什么都不用做**，Cloudflare 收到推送自动构建发布，1~3 分钟上线。

> 本地跑 `build.py` 是为了自己先看一眼，**不是必须**。但改了 `build.py` 本身或 `_redirects` 时建议跑一下，能提前发现语法错误。

### 6.2 数据更新

**不用你管**，GitHub Actions 每 6 小时自己抓、自己提交、自动触发 Cloudflare 重建。

### 6.3 手动改数据的场景

万一要手动补一次数据（比如 2rtk.net 刚上线想立刻看到）：

```bash
# 本地自带一份 ntrip_servers.ini（含密码），跑完直接推
python lary.py
python scripts/fetch_tle.py
python scripts/build.py --files-json
git add data/ && git commit -m "data: 手动补一轮" && git push
```

### 6.4 回滚

Cloudflare Pages → **Deployments** → 找到上次好的那次 → 右侧 **⋯** → **Rollback to this deployment**。秒级生效，不用改 git。

---

## 7. 排错对照表

| 现象 | 原因 | 解决 |
|---|---|---|
| push 报 `rejected (fetch first)` | 建仓库时勾了 README/LICENSE | `git pull --rebase origin main` 后再 push |
| push 报 `403` / 认证失败 | 密码位置填了登录密码 | 换成 Personal Access Token |
| Actions 报 `Permission denied to github-actions[bot]` | 工作流默认只读 | Settings → Actions → General → Workflow permissions → Read and write |
| Actions 成功但仓库没有新提交 | 数据本轮无变化 | 正常，日志会写「数据无变化，跳过提交」 |
| Cloudflare 构建报 `/bin/sh: 3: 3.11: not found` | `.python-version` 里写了注释，整段被当成版本号 | 该文件**只能有一行版本号**，任何 `#` 注释都会导致解析失败 |
| Cloudflare 构建报 `python: command not found` | Build command 写成了 `python` | 改成 `sh scripts/cf-build.sh` |
| Cloudflare 构建报 `No such file or directory: dist` | 输出目录填错 | 填 `dist`（无斜杠） |
| 构建成功但页面 404 | 输出目录指向了 `site` | 改为 `dist` |
| 页面能开但地图空白 | 浏览器控制台报 Cesium 加载失败 | 检查 `/config.js` 是否 200；或先不配 Token 用公共图源 |
| 站点数据不更新，但 Actions 是绿的 | 2rtk 源连不上，走了「沿用旧数据」 | 看 Actions Summary 里哪一路 `⚠️ 失败` |
| 访问旧链接 `/rtkbase/` 变 404 | `_redirects` 没被复制到 dist 根 | 看构建日志有没有「已复制 Cloudflare 配置 _redirects」 |
| Cloudflare 显示域名 Pending 一直不动 | NS 还没生效 | 用 `nslookup -type=ns 2rtk.com` 查是否已指向 Cloudflare |

---

## 8. 一页速查（做完对照打勾）

**GitHub**
- [ ] 建仓库时三个初始化选项全不勾
- [ ] `git remote add origin` + `git push -u origin main`
- [ ] 仓库里能看到 `data/`、`site/`、`.github/`、`.python-version`
- [ ] 仓库里**看不到** `dist/`、`ntrip_servers.ini`、`config.js`
- [ ] Actions → Collect NTRIP Data → Run workflow，跑通并产生提交
- [ ] Settings → Actions → Workflow permissions 设为 Read and write

**Cloudflare**
- [ ] 域名 NS 已托管到 Cloudflare（绑自定义域名前必须）
- [ ] Pages 项目连接 `2rtkcom` 仓库
- [ ] Build command = `sh scripts/cf-build.sh`
- [ ] Build output directory = `dist`
- [ ] Framework preset = None
- [ ] 首次部署成功，`xxx.pages.dev` 能访问
- [ ] Custom domains 绑定 `2rtk.com` 和 `www.2rtk.com`，状态 Active
- [ ] 开了 Always Use HTTPS
- [ ] （可选）加了 `CESIUM_ION_TOKEN` 并重新部署

---

## 9. 三句话总结

1. **放 GitHub 的**：所有源码 + `data/*.json` + `_redirects`/`_headers` + `.python-version` + workflow 文件。不放 `dist/`、不放带密码的 `.ini`。
2. **放 Cloudflare 的**：只有三样——构建命令 `sh scripts/cf-build.sh`、输出目录 `dist`、以及 `CESIUM_ION_TOKEN` 这个环境变量。其余 Cloudflare 什么都不用配。
3. **数据怎么搭上 GitHub 推送**：Actions 每 6 小时抓完直接 commit 到 `data/`，Cloudflare 监听这个仓库的 push 自动重建。不需要任何后端、数据库或 API。
