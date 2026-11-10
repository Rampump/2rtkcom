"""Cloudflare Pages 构建脚本。

职责：
1. 由环境变量 CESIUM_ION_TOKEN 生成 dist/config.js（token 不进代码库）
2. 扫描 data/*.json 生成 data/files.json（避免手工维护遗漏）
3. 组装 dist/ 产物目录（index.html、images/、data/）

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

# files.json 不收录的自身元数据文件
EXCLUDED = {'files.json', 'meta.json'}


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
    if ion_token:
        print("[ok] 已从 CESIUM_ION_TOKEN 注入 Ion Token")
    elif tdt_token:
        print("[ok] 未设置 Ion Token，已注入 TIANDITU_TOKEN 作为底图")
    else:
        print("[warn] 未设置任何底图凭证（CESIUM_ION_TOKEN / TIANDITU_TOKEN），前端仅显示站点与卫星")
    content = (
        '/* 由 scripts/build.py 生成，请勿手工编辑或提交 */\n'
        'window.__2RTK_CONFIG = '
        + json.dumps({'cesiumIonToken': ion_token, 'tiandituToken': tdt_token}, ensure_ascii=False)
        + ';\n'
    )
    with open(os.path.join(dist_dir, 'config.js'), 'w', encoding='utf-8') as f:
        f.write(content)
    # 同步一份到根目录，便于本地直接 python -m http.server 预览（已在 .gitignore 中排除）
    with open(os.path.join(ROOT, 'config.js'), 'w', encoding='utf-8') as f:
        f.write(content)


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

    # 站点主体：替换构建版本号，避免 config.js 被浏览器长期缓存
    build_id = datetime.now().strftime('%Y%m%d%H%M%S')
    with open(os.path.join(ROOT, 'index.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace('__BUILD_ID__', build_id)
    with open(os.path.join(DIST_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
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

    write_config_js(DIST_DIR)
    print(f"[ok] 构建完成 -> {DIST_DIR}")


if __name__ == '__main__':
    if '--files-json' in sys.argv:
        write_files_json()
    else:
        build()
