#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/meta.json 汇总成一张 markdown 表，打印到 stdout。

用途：
  · GitHub Actions 里追加到 $GITHUB_STEP_SUMMARY，每轮采集完能直接在
    Actions 页面看到「哪个源成功、哪个源沿用了上次数据、各有多少站点」
  · 本地跑完 lary.py 后也能直接执行，快速确认采集结果

用法：
  python scripts/summarize.py            # 打印到终端
  python scripts/summarize.py --github   # 写入 $GITHUB_STEP_SUMMARY
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "data", "meta.json")
TLE = os.path.join(ROOT, "data", "tle-gnss.txt")


def build(meta):
    lines = ["### 本轮采集结果", ""]
    lines.append("| 数据源 | 文件 | 状态 | 站点数 |")
    lines.append("| --- | --- | --- | --- |")

    for s in meta.get("sources", []):
        ok = s.get("ok")
        # 失败时 lary.py 不会覆盖旧文件，前端仍然能拿到上一轮的数据
        state = "✅ 成功" if ok else "⚠️ 失败（沿用上次数据）"
        lines.append("| {} | {} | {} | {} |".format(
            s.get("name", "-"), s.get("file", "-"), state, s.get("station_count", 0)
        ))

    igs_ok = meta.get("igs_network", {}).get("ok")
    lines.append("| IGS 坐标 | IGSNetwork.json | {} | - |".format(
        "✅ 成功" if igs_ok else "⚠️ 失败（沿用上次数据）"))
    lines.append("| GNSS TLE | tle-gnss.txt | {} | - |".format(
        "✅ 已更新" if os.path.exists(TLE) else "⚠️ 缺失"))

    lines.append("")
    lines.append("更新时间：{}".format(meta.get("last_update", "未知")))
    return "\n".join(lines)


def tle_age_hours():
    """TLE 文件多久前更新的，给个直观提醒（超过 24 小时说明一直在失败）"""
    if not os.path.exists(TLE):
        return None
    import time
    return (time.time() - os.path.getmtime(TLE)) / 3600.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github", action="store_true",
                    help="写入 $GITHUB_STEP_SUMMARY，而不是打印")
    args = ap.parse_args()

    if not os.path.exists(META):
        print("data/meta.json 不存在，先跑一次 python lary.py", file=sys.stderr)
        return 1

    with open(META, "r", encoding="utf-8") as f:
        meta = json.load(f)

    text = build(meta)

    age = tle_age_hours()
    if age is not None and age > 24:
        text += "\n\n> TLE 已 {:.0f} 小时未更新，检查 CelesTrak 是否限流。".format(age)

    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if args.github:
        if not target:
            print("未在 Actions 环境中（$GITHUB_STEP_SUMMARY 为空）", file=sys.stderr)
            print(text)
            return 0
        with open(target, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        return 0

    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
