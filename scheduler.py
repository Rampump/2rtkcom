"""定时调度器：每 6 小时执行一次 lary.main() 采集 NTRIP 数据。

用法：
    python scheduler.py            # 启动后立即采集一次，之后每 6 小时采集
    python scheduler.py --once     # 只采集一次后退出（用于测试）

生产环境（Linux 云服务器）建议改用系统级定时任务，本脚本用于本地/无 cron 环境。
"""
import sys
import time
import traceback

import lary

INTERVAL_SECONDS = 6 * 3600  # 6 小时


def run_once():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始采集...")
    try:
        lary.main()
        print("采集完成。")
    except Exception as e:
        print(f"采集出错: {e}")
        traceback.print_exc()


def main():
    if '--once' in sys.argv:
        run_once()
        return

    print(f"调度器已启动，每 {INTERVAL_SECONDS // 3600} 小时采集一次。")
    while True:
        run_once()
        print(f"下次采集: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + INTERVAL_SECONDS))}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
