"""Cloudflare Pages 构建脚本。

职责：
1. 由环境变量生成 dist/config.js（Ion / 天地图 token 不进代码库）
2. 扫描 data/*.json 生成 data/files.json（避免手工维护遗漏）
3. 替换 index.html 与 site/ 下内容页中的 __SITE_ORIGIN__ / __BUILD_ID__ 占位符
4. 生成 robots.txt 与 sitemap.xml（SEO，收录地图页与全部内容页）
5. 组装 dist/ 产物目录（index.html、site 内容页、assets/、images/、data/）

环境变量（均为可选）：
    CESIUM_ION_TOKEN   Cesium Ion 访问令牌
    TIANDITU_TOKEN     天地图「浏览器端」Key
    SITE_ORIGIN        站点域名，默认 https://map.2rtk.com
    HOME_ORIGIN        首页站域名，默认 https://2rtk.com（内容页已并入本站，暂仅保留配置）

用法：
    python scripts/build.py                 # 完整构建到 dist/
    python scripts/build.py --files-json    # 仅刷新 data/files.json（供 Actions 采集后调用）
"""
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
DIST_DIR = os.path.join(ROOT, 'dist')
SITE_DIR = os.path.join(ROOT, 'site')

# files.json 不收录的自身元数据文件
EXCLUDED = {'files.json', 'meta.json'}

DEFAULT_SITE_ORIGIN = 'https://map.2rtk.com'
DEFAULT_HOME_ORIGIN = 'https://2rtk.com'

# 内容页清单：目录名 -> (sitemap 权重, 更新频率)
# 顺序即 sitemap 中的顺序，首页单独处理
PAGES = [
    ('rtk-base', '0.9', 'monthly'),
    ('caster', '0.9', 'monthly'),
    ('what-is-rtk', '0.8', 'monthly'),
    ('test-caster', '0.7', 'weekly'),
    ('about', '0.4', 'yearly'),
]


def get_site_origin():
    """地图站根地址，去掉末尾斜杠"""
    origin = os.environ.get('SITE_ORIGIN', '').strip() or DEFAULT_SITE_ORIGIN
    return origin.rstrip('/')


def get_home_origin():
    """首页站根地址（教程 / 2RTK Server / Caster 页面所在域名）"""
    origin = os.environ.get('HOME_ORIGIN', '').strip() or DEFAULT_HOME_ORIGIN
    return origin.rstrip('/')


def collect_json_files():
    """扫描 data 目录下的站点数据文件，返回排序后的文件名列表"""
    if not os.path.isdir(DATA_DIR):
        return []
    names = []
    for name in os.listdir(DATA_DIR):
        if not name.endswith('.json'):
            continue
        if name in EXCLUDED:
            continue
        path = os.path.join(DATA_DIR, name)
        # 校验 JSON 合法性，坏文件不进入列表，避免前端整体加载失败
        try:
            with open(path, 'r', encoding='utf-8') as f:
                json.load(f)
        except Exception as exc:
            print(f"[skip] {name} JSON 无效: {exc}")
            continue
        names.append(name)
    return sorted(names)


def write_files_json():
    names = collect_json_files()
    target = os.path.join(DATA_DIR, 'files.json')
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f"[ok] data/files.json 已更新，共 {len(names)} 个数据文件")
    return names


def write_config_js(dist_dir):
    ion_token = os.environ.get('CESIUM_ION_TOKEN', '').strip()
    tdt_token = os.environ.get('TIANDITU_TOKEN', '').strip()
    origin = get_site_origin()
    home = get_home_origin()

    if ion_token:
        print("[ok] 已注入 CESIUM_ION_TOKEN")
    if tdt_token:
        print("[ok] 已注入 TIANDITU_TOKEN")
    if not ion_token and not tdt_token:
        print("[info] 未配置 Ion / 天地图凭证，将使用公共图源（Esri 影像 / Esri 街道 / OSM）")
    print(f"[info] 地图站: {origin} | 首页站: {home}")

    payload = {
        'cesiumIonToken': ion_token,
        'tiandituToken': tdt_token,
        'siteOrigin': origin,
        'homeOrigin': home,
    }
    content = (
        '/* 由 scripts/build.py 生成，请勿手工编辑或提交 */\n'
        'window.__2RTK_CONFIG = '
        + json.dumps(payload, ensure_ascii=False)
        + ';\n'
    )
    with open(os.path.join(dist_dir, 'config.js'), 'w', encoding='utf-8') as f:
        f.write(content)
    # 同步一份到根目录，便于本地直接 python -m http.server 预览（已在 .gitignore 中排除）
    with open(os.path.join(ROOT, 'config.js'), 'w', encoding='utf-8') as f:
        f.write(content)


def write_seo_files(dist_dir):
    """生成 robots.txt 与 sitemap.xml。

    地图页与内容页现在同属一个站点（SITE_ORIGIN），sitemap 统一收录。
    """
    origin = get_site_origin()

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {origin}/sitemap.xml\n"
    )
    with open(os.path.join(dist_dir, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(robots)

    today = datetime.now().strftime('%Y-%m-%d')
    urls = [('/', '1.0', 'daily')]
    urls += [('/%s/' % slug, prio, freq) for slug, prio, freq in PAGES]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, prio, freq in urls:
        lines += [
            '  <url>',
            f'    <loc>{origin}{path}</loc>',
            f'    <lastmod>{today}</lastmod>',
            f'    <changefreq>{freq}</changefreq>',
            f'    <priority>{prio}</priority>',
            '  </url>',
        ]
    lines.append('</urlset>')
    with open(os.path.join(dist_dir, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"[ok] 已生成 robots.txt 与 sitemap.xml（{len(urls)} 条 URL）")


def render_pages(dist_dir, build_id, origin):
    """把 site/ 下的静态内容页渲染到 dist/，并替换占位符。

    site/ 目录结构与最终 URL 一一对应：
        site/assets/site.css      -> /assets/site.css
        site/what-is-rtk/index.html -> /what-is-rtk/
    """
    if not os.path.isdir(SITE_DIR):
        print("[warn] 未找到 site/ 目录，跳过内容页")
        return 0

    count = 0
    for dirpath, _dirnames, filenames in os.walk(SITE_DIR):
        rel_dir = os.path.relpath(dirpath, SITE_DIR)
        out_dir = dist_dir if rel_dir == '.' else os.path.join(dist_dir, rel_dir)
        os.makedirs(out_dir, exist_ok=True)

        for name in filenames:
            src = os.path.join(dirpath, name)
            dst = os.path.join(out_dir, name)
            if name.endswith(('.html', '.js', '.css', '.xml', '.txt')):
                with open(src, 'r', encoding='utf-8') as f:
                    text = f.read()
                text = text.replace('__SITE_ORIGIN__', origin)
                text = text.replace('__BUILD_ID__', build_id)
                leftover = [p for p in ('__SITE_ORIGIN__', '__BUILD_ID__') if p in text]
                if leftover:
                    raise SystemExit(f"[fail] {name} 中仍有未替换的占位符: {leftover}")
                with open(dst, 'w', encoding='utf-8') as f:
                    f.write(text)
                if name.endswith('.html'):
                    count += 1
            else:
                shutil.copy2(src, dst)
    print(f"[ok] 内容页渲染完成，共 {count} 个 HTML 页面")
    return count


def ensure_optional_data():
    """2rtk.json 缺失时生成空数组占位，避免前端按钮 404"""
    path = os.path.join(DATA_DIR, '2rtk.json')
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('[]\n')
        print("[ok] data/2rtk.json 缺失，已生成空占位")


def build():
    write_files_json()
    ensure_optional_data()
    # 占位文件需重新纳入 files.json
    write_files_json()

    # 增量覆盖而非整目录删除，避免触发文件保护策略
    os.makedirs(DIST_DIR, exist_ok=True)

    # 站点主体：替换站点域名占位符与构建版本号
    build_id = datetime.now().strftime('%Y%m%d%H%M%S')
    origin = get_site_origin()
    home = get_home_origin()
    with open(os.path.join(ROOT, 'index.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace('__SITE_ORIGIN__', origin)
    html = html.replace('__HOME_ORIGIN__', home)
    html = html.replace('__BUILD_ID__', build_id)
    with open(os.path.join(DIST_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

    # 兜底：源码里若残留占位符，说明有遗漏，直接报错避免线上出现脏字符串
    leftover = [p for p in ('__SITE_ORIGIN__', '__HOME_ORIGIN__', '__BUILD_ID__') if p in html]
    if leftover:
        raise SystemExit(f"[fail] index.html 中仍有未替换的占位符: {leftover}")

    # 图片资源
    src_images = os.path.join(ROOT, 'images')
    if os.path.isdir(src_images):
        shutil.copytree(src_images, os.path.join(DIST_DIR, 'images'), dirs_exist_ok=True)
    # 数据文件
    dst_data = os.path.join(DIST_DIR, 'data')
    os.makedirs(dst_data, exist_ok=True)
    for name in os.listdir(DATA_DIR):
        if name.endswith('.json'):
            shutil.copy2(os.path.join(DATA_DIR, name), os.path.join(dst_data, name))

    # 卫星 TLE（前端优先读这份本地文件，避免被 CelesTrak 限流时画不出卫星）
    tle_src = os.path.join(DATA_DIR, 'tle-gnss.txt')
    if os.path.exists(tle_src):
        shutil.copy2(tle_src, os.path.join(dst_data, 'tle-gnss.txt'))
        print(f"[ok] 已同步 data/tle-gnss.txt（{os.path.getsize(tle_src) / 1024:.1f} KB）")
    else:
        print("[warn] 缺少 data/tle-gnss.txt，前端将回退到 CelesTrak 实时接口（容易被限流）")
        print("       执行 python scripts/fetch_tle.py 生成")

    write_config_js(DIST_DIR)
    render_pages(DIST_DIR, build_id, origin)
    write_seo_files(DIST_DIR)
    print(f"[ok] 构建完成 -> {DIST_DIR}")


if __name__ == '__main__':
    if '--files-json' in sys.argv:
        write_files_json()
    else:
        build()
