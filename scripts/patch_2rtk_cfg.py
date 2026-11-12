#!/usr/bin/env python3
"""用 GitHub Secrets 里的账号覆盖 ntrip_servers.ini 的 [2rtk] 段。

只在配了 NTRIP_2RTK_HOST/USERNAME 时由 CI 调用；
ci.ini 默认走匿名源表，不需要跑这个脚本。

用法: python scripts/patch_2rtk_cfg.py <host> <port> <username> <password>
"""
import configparser
import sys

SECTION = '2rtk'
CONFIG_PATH = 'ntrip_servers.ini'


def main():
    if len(sys.argv) != 5:
        print('用法: patch_2rtk_cfg.py <host> <port> <username> <password>', file=sys.stderr)
        return 2

    host, port, user, password = sys.argv[1:5]

    cfg = configparser.ConfigParser()
    if not cfg.read(CONFIG_PATH, encoding='utf-8'):
        print(f'ERROR: 读不到 {CONFIG_PATH}', file=sys.stderr)
        return 1

    if not cfg.has_section(SECTION):
        cfg.add_section(SECTION)

    cfg[SECTION].update({
        'host': host,
        'port': port,
        'enabled': 'true',
        'output_prefix': SECTION,
        'address': 'https://2rtk.com',
        'username': user,
        'password': password,
    })

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        cfg.write(f)

    print(f'[2rtk] 已更新为 {host}:{port}（用户 {user}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
