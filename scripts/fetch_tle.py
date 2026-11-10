#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 GNSS 卫星 TLE，输出标准三行格式到 data/tle-gnss.txt。

为什么要有本地文件：
  · celestrak.org 有下载频率限制，同一个 IP 拉太多次会被封 2 小时
    （被封时直接返回 403，前端就一颗卫星都画不出来）
  · 前端改成「先读本地文件，失败再直连 CelesTrak」，
    这样即使 CelesTrak 把访客 IP 封了，卫星图层依然正常

数据源优先级：
  1. CelesTrak 官方 GNSS 组（最新、最权威）
  2. tle.ivanstanojevic.me（Space-Track 镜像，按名称搜索各星座）

用法：
  python scripts/fetch_tle.py            # 拉取并覆盖 data/tle-gnss.txt
  python scripts/fetch_tle.py --check    # 只报告本地文件是否过期
"""

import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "tle-gnss.txt")

UA = "2rtk-map/1.0 (+https://2rtk.com; GNSS base station map)"
TIMEOUT = 30

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP=gnss&FORMAT=tle"

# 镜像源按星座名称搜索，覆盖 GPS / GLONASS / Galileo / BeiDou / QZSS / NavIC
MIRROR_QUERIES = [
    "GPS", "NAVSTAR", "GLONASS", "GALILEO", "BEIDOU", "QZS", "MICHIBIKI", "IRNSS",
]

# 只保留真正的导航卫星（镜像源搜索是模糊匹配，会带出通信星）
GNSS_NAME_HINTS = (
    "GPS", "NAVSTAR", "BIIR", "BIIRM", "BIIF", "BIII",
    "GLONASS", "GALILEO", "BEIDOU", "COMPASS", "BD-",
    "QZS", "MICHIBIKI", "IRNSS", "NVS-",
)


def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_celestrak():
    raw = http_get(CELESTRAK).decode("utf-8", "ignore")
    if "403" in raw[:200] and "<html" in raw[:400].lower():
        raise RuntimeError("CelesTrak 返回 403（IP 被限流）")
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    if not lines or not lines[0].strip()[0].isalnum():
        raise RuntimeError("CelesTrak 返回内容不是 TLE")
    # 校验 3 行一组
    if len(lines) % 3 != 0:
        raise RuntimeError("CelesTrak TLE 行数不是 3 的倍数：%d" % len(lines))
    print("[tle] CelesTrak 成功：%d 颗" % (len(lines) // 3))
    return lines


def fetch_mirror():
    seen = {}
    for q in MIRROR_QUERIES:
        page = 1
        while page <= 3:
            url = ("https://tle.ivanstanojevic.me/api/tle?%s"
                   % urllib.parse.urlencode({"search": q, "page": page, "page_size": 100}))
            try:
                payload = json.loads(http_get(url).decode("utf-8", "ignore"))
            except Exception as exc:  # 网络/JSON 异常只影响这一页
                print("[tle] 镜像 %s 第 %d 页失败：%s" % (q, page, exc))
                break

            members = payload.get("member") or []
            if not members:
                break

            for m in members:
                name = (m.get("name") or "").strip()
                l1 = (m.get("line1") or "").strip()
                l2 = (m.get("line2") or "").strip()
                if not name or not l1.startswith("1 ") or not l2.startswith("2 "):
                    continue
                if not any(h in name.upper() for h in GNSS_NAME_HINTS):
                    continue
                seen[m.get("satelliteId") or name] = (name, l1, l2)

            if len(members) < 100:
                break
            page += 1
            time.sleep(0.3)

    if not seen:
        raise RuntimeError("镜像源未取到任何 GNSS 卫星")

    out = []
    for name, l1, l2 in seen.values():
        out.extend([name, l1, l2])
    print("[tle] 镜像源成功：%d 颗" % len(seen))
    return out


def write_tle(lines):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 2RTK GNSS TLE  生成时间 %s\n" % stamp)
        fh.write("# 数据来源 CelesTrak / Space-Track 镜像，仅供可视化参考\n")
        for ln in lines:
            fh.write(ln + "\n")
    size = os.path.getsize(OUT)
    print("[tle] 已写入 %s（%d 行，%.1f KB）" % (OUT, len(lines), size / 1024.0))


def local_age_hours():
    if not os.path.exists(OUT):
        return None
    mtime = dt.datetime.fromtimestamp(os.path.getmtime(OUT), dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - mtime).total_seconds() / 3600.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查本地文件是否过期")
    ap.add_argument("--max-age", type=float, default=12.0, help="超过多少小时算过期（默认 12）")
    args = ap.parse_args()

    age = local_age_hours()
    if args.check:
        if age is None:
            print("[tle] 本地文件不存在")
            return 1
        print("[tle] 本地文件 %.1f 小时前生成（阈值 %.0f 小时）" % (age, args.max_age))
        return 0 if age <= args.max_age else 2

    if age is not None and age <= 1.0:
        print("[tle] 本地文件 %.1f 小时前刚更新过，跳过" % age)
        return 0

    for fetcher in (fetch_celestrak, fetch_mirror):
        try:
            write_tle(fetcher())
            return 0
        except Exception as exc:
            print("[tle] %s 失败：%s" % (fetcher.__name__, exc))

    print("[tle] 所有数据源都失败，保留现有文件")
    return 1


if __name__ == "__main__":
    sys.exit(main())
