#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 IGS 卫星元数据（SINEX），输出 data/sat-meta.json。

数据来源：
  https://files.igs.org/pub/station/general/igs_satellite_metadata.snx

为什么要这个文件：
  TLE 里只有轨道根数，没有 SVN/PRN、卫星型号、发射日期、轨道面槽位这些
  “静态身份信息”。这些字段由 IGS 多 GNSS 工作组维护，权威且长期不变，
  不需要任何 API key，也不受频率限制，适合和 TLE 一起随仓库部署。

输出结构（按 NORAD 号索引，前端用 TLE 的 satrec.satnum 直接查）：
  {
    "44865": {
      "svn": "C042", "prn": "C42", "block": "BDS-3",
      "cospar": "2019-061A", "launch": "2019-09-22",
      "plane": "M", "slot": "3",
      "mass_kg": 1014.0, "tx_power_w": 60,
      "freq_ch": null
    }
  }

用法：
  python scripts/fetch_satmeta.py            # 抓取并覆盖 data/sat-meta.json
  python scripts/fetch_satmeta.py --check    # 只报告本地文件是否过期
"""

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "sat-meta.json")

URL = "https://files.igs.org/pub/station/general/igs_satellite_metadata.snx"
UA = "2rtk-map/1.0 (+https://2rtk.com; GNSS base station map)"
TIMEOUT = 60

DATE = r"\d{4}:\d{3}:\d{5}"
END_OF_TIME = "0000:000:00000"

RE_IDENT = re.compile(r"^\s+(\S+)\s+(\d{4}-\d{3}[A-Z]*)\s+(\d+)\s+(\S+)\s*(.*)$")
RE_PRN = re.compile(r"^\s+(\S+)\s+" + DATE + r"\s+" + DATE + r"\s+(\S+)")
RE_PLANE = re.compile(r"^\s+(\S+)\s+" + DATE + r"\s+" + DATE + r"\s+(\S+)\s+(\S+)")
RE_FREQ = re.compile(r"^\s+(\S+)\s+" + DATE + r"\s+" + DATE + r"\s+(-?\d+)")
RE_MASS = re.compile(r"^\s+(\S+)\s+" + DATE + r"\s+" + DATE + r"\s+([0-9.]+)")
RE_TX = re.compile(r"^\s+(\S+)\s+" + DATE + r"\s+" + DATE + r"\s+([0-9.]+)")
RE_LAUNCH = re.compile(r"Launched\s+(\d{4}-\d{2}-\d{2})")


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def blocks(text, name):
    """取出 SINEX 里 +NAME ... -NAME 之间的数据行（去掉注释行）。"""
    out = []
    inside = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("+" + name):
            inside = True
            continue
        if s.startswith("-" + name):
            inside = False
            continue
        if inside and s and not s.startswith("*"):
            out.append(line)
    return out


def parse_active(rows, regex, cast=None):
    """同一个 SVN 会有多条历史记录，优先取 Valid_To=无穷 的那条。"""
    active, latest = {}, {}
    for line in rows:
        m = regex.match(line)
        if not m:
            continue
        svn = m.group(1)
        vals = [g for g in m.groups()[1:]]
        if cast:
            try:
                vals = [cast(vals[0])] + vals[1:]
            except (TypeError, ValueError):
                continue
        if END_OF_TIME in line:
            active[svn] = vals
        latest[svn] = vals
    result = {}
    result.update(latest)
    result.update(active)
    return result


def build():
    raw = http_get(URL).decode("utf-8", "ignore")
    if "SNX" not in raw[:120]:
        raise RuntimeError("返回内容不是 SINEX（可能被限流）")

    ident = {}
    for line in blocks(raw, "SATELLITE/IDENTIFIER"):
        m = RE_IDENT.match(line)
        if not m:
            continue
        svn, cospar, satcat, blk, comment = m.groups()
        launch = RE_LAUNCH.search(comment)
        ident[svn] = {
            "cospar": cospar if re.match(r"^\d{4}-\d{3}[A-Z]*$", cospar) else None,
            "norad": satcat,
            "block": blk,
            "launch": launch.group(1) if launch else None,
        }

    prn = {svn: v[0] for svn, v in parse_active(blocks(raw, "SATELLITE/PRN"), RE_PRN).items()}
    plane = parse_active(blocks(raw, "SATELLITE/PLANE"), RE_PLANE)
    freq = parse_active(blocks(raw, "SATELLITE/FREQUENCY_CHANNEL"), RE_FREQ)
    mass = parse_active(blocks(raw, "SATELLITE/MASS"), RE_MASS, cast=float)
    tx = parse_active(blocks(raw, "SATELLITE/TX_POWER"), RE_TX, cast=float)

    out = {}
    for svn, info in ident.items():
        norad = info.get("norad")
        if not norad:
            continue
        p = plane.get(svn)
        f = freq.get(svn)
        m_ = mass.get(svn)
        t_ = tx.get(svn)
        rec = {
            "svn": svn,
            "prn": prn.get(svn),
            "block": info.get("block"),
            "cospar": info.get("cospar"),
            "launch": info.get("launch"),
            "plane": p[0] if p else None,
            "slot": p[1] if p else None,
            "mass_kg": m_[0] if m_ else None,
            "tx_power_w": t_[0] if t_ else None,
            "freq_ch": f[0] if f else None,
        }
        out[norad] = rec

    return out


def write(data):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"_generated": stamp}
    payload.update(data)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    size = os.path.getsize(OUT)
    print("[satmeta] 已写入 %s（%d 条，%.1f KB）" % (OUT, len(data), size / 1024.0))


def local_age_hours():
    """用 JSON 里的 _generated 判断新鲜度。
    CI 的 actions/checkout 会把 mtime 重置成「刚刚」，用 mtime 会导致永远跳过。"""
    if not os.path.exists(OUT):
        return None
    try:
        with io.open(OUT, "r", encoding="utf-8") as fh:
            stamp = json.load(fh).get("_generated")
        if stamp:
            t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        pass
    return (dt.datetime.now(dt.timezone.utc)
            - dt.datetime.fromtimestamp(os.path.getmtime(OUT), dt.timezone.utc)).total_seconds() / 3600.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查本地文件是否过期")
    ap.add_argument("--max-age", type=float, default=48.0, help="超过多少小时算过期（默认 48）")
    ap.add_argument("--force", action="store_true", help="忽略新鲜度检查，强制重拉")
    args = ap.parse_args()

    age = local_age_hours()

    if args.check:
        if age is None:
            print("[satmeta] 本地文件不存在")
            return 1
        print("[satmeta] 本地文件 %.1f 小时前生成（阈值 %.0f 小时）" % (age, args.max_age))
        return 0 if age <= args.max_age else 2

    # 元数据变化很慢，48 小时内不重复拉
    if not args.force and age is not None and age <= 48.0:
        print("[satmeta] 本地文件 %.1f 小时前刚更新过，跳过" % age)
        return 0

    try:
        write(build())
        return 0
    except Exception as exc:
        print("[satmeta] 拉取失败：%s（保留现有文件）" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
