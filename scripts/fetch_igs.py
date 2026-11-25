"""刷新 data/IGSNetwork.json：从 network.igs.org 公共 API 拉当前 IGS 现网站点。

背景：
    原来的 IGSNetwork.json 是 IGS 站志（station log）的历史存档，共 776 站，
    比官方现网（约 535 站）多出两百多个已退役站点，前端点进去会 404。
    这里改成直接对齐官方现网列表，同时把旧文件里仍然有效的字段
    （天线安装日期、时钟、产物等）合并保留，避免丢失信息。

接口（均已实测，对任意 Origin 开放 CORS）：
    GET /api/public/stations/?length=500&start=N   列表，Datatables 分页
    GET /api/public/equipment/{SITE9}/             设备历史，补接收机安装日期

用法：
    python scripts/fetch_igs.py             # 拉取并覆盖 data/IGSNetwork.json
    python scripts/fetch_igs.py --dry-run   # 只统计，不写文件
"""
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, 'data', 'IGSNetwork.json')

API = 'https://network.igs.org/api/public'
UA = '2rtk.com station sync (+https://2rtk.com)'
PAGE = 500
WORKERS = 8


def api_get(path, timeout=30):
    req = urllib.request.Request(API + path, headers={
        'User-Agent': UA,
        'Accept': 'application/json',
        'Origin': 'https://2rtk.com',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError('HTTP %s %s' % (resp.status, path))
        return json.loads(resp.read().decode('utf-8'))


def fetch_rows():
    """翻页拉全部现网站点"""
    rows = []
    start = 0
    total = None
    while True:
        page = api_get('/stations/?length=%d&start=%d' % (PAGE, start))
        data = page.get('data') or []
        if total is None:
            total = page.get('recordsFiltered')
        rows.extend(data)
        if len(data) < PAGE:
            break
        start += PAGE
        if total and start >= total:
            break
    print('[ok] 现网站点 %d 条（接口 recordsFiltered=%s）' % (len(rows), total))
    return rows


def num(v, digits=6):
    if v is None or v == '':
        return None
    try:
        return round(float(v), digits)
    except (TypeError, ValueError):
        return None


def build_entry(row, old):
    """把 API 行转成前端 normalizeIgsStations() 认识的 PascalCase 结构"""
    name = row.get('name') or ''
    llh = row.get('llh') or [None, None, None]
    xyz = row.get('xyz') or [None, None, None]
    lat, lon, height = num(llh[0]), num(llh[1]), num(llh[2], 3)
    if lat is None or lon is None:
        return None, 'no coords'

    old = old or {}
    rec = dict(old.get('Receiver') or {})
    ant = dict(old.get('Antenna') or {})

    # 接收机
    rec['Name'] = row.get('receiver_type') or rec.get('Name') or ''
    systems = row.get('satellite_system')
    if isinstance(systems, list) and systems:
        rec['SatelliteSystem'] = '+'.join(systems)
    rec['SerialNumber'] = row.get('serial_number') or rec.get('SerialNumber') or ''
    rec['FirmwareVersion'] = row.get('firmware') or rec.get('FirmwareVersion') or ''
    rec.setdefault('DateInstalled', '')

    # 天线
    ant['Name'] = row.get('antenna_type') or ant.get('Name') or ''
    ant['Radome'] = row.get('radome_type') or ant.get('Radome') or ''
    ant['SerialNumber'] = row.get('antenna_serial_number') or ant.get('SerialNumber') or ''
    marker = row.get('antenna_marker_une')
    if isinstance(marker, list) and len(marker) == 3:
        ant['MarkerUp'] = marker[0]
        ant['MarkerNorth'] = marker[1]
        ant['MarkerEast'] = marker[2]
    if row.get('antcal'):
        ant['Calibration'] = row['antcal']
    ant.setdefault('DateInstalled', '')

    entry = dict(old)                       # 保留旧文件里的 Clock / Product / RealTime 等
    entry['CountryOrRegion'] = row.get('country') or old.get('CountryOrRegion') or ''
    entry['City'] = row.get('city') or old.get('City') or ''
    entry['State'] = row.get('state') or old.get('State') or ''
    entry['DOMES'] = row.get('domes_number') or old.get('DOMES') or ''
    entry['DataCenter'] = row.get('data_center') or old.get('DataCenter') or ''
    entry['Networks'] = [n.get('name') for n in (row.get('networks') or []) if n and n.get('name')]
    entry['Agencies'] = [a.get('shortname') or a.get('name')
                         for a in (row.get('agencies') or []) if a]
    entry['FrequencyStandard'] = row.get('frequency_standard') or old.get('FrequencyStandard') or ''
    entry['JoinDate'] = row.get('join_date') or old.get('JoinDate') or ''
    entry['LastData'] = row.get('last_data_time') or old.get('LastData') or ''
    entry['LastDataAge'] = row.get('last_data')
    entry['LastRinex2'] = row.get('last_rinex2') or ''
    entry['LastRinex3'] = row.get('last_rinex3') or ''
    entry['LastRinex4'] = row.get('last_rinex4') or ''
    entry['RealTimeSystems'] = row.get('real_time_systems') or []
    entry['TideGauges'] = [
        {'Name': g.get('name'), 'Distance': g.get('distance'), 'Link': g.get('link')}
        for g in (row.get('tide_gauges') or []) if g and g.get('name')
    ]
    entry['Status'] = row.get('status')

    entry['X'], entry['Y'], entry['Z'] = num(xyz[0], 3), num(xyz[1], 3), num(xyz[2], 3)
    entry['Latitude'] = lat
    entry['Longitude'] = lon
    entry['Height'] = height
    entry['Receiver'] = rec
    entry['Antenna'] = ant
    return entry, None


def fill_install_dates(sites):
    """对缺天线/接收机安装日期的站点补一次设备历史（只取最新一条）"""
    def one(site):
        try:
            equip = api_get('/equipment/%s/' % site)
        except Exception as exc:
            return site, None, str(exc)
        if not isinstance(equip, list) or not equip:
            return site, None, 'empty'
        latest = equip[0]
        body = latest[1] if isinstance(latest, list) and len(latest) > 1 else {}
        rcv = (body.get('receiver') or {}).get('installed') or ''
        ant = (body.get('antenna') or {}).get('installed') or ''
        return site, (rcv[:10], ant[:10]), None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(one, sites))


def refresh(path=DATA_PATH, dry_run=False):
    """拉取现网并写回文件，返回是否成功（供 lary.py 与命令行共用）"""
    old = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            old = json.load(f)
    print('[info] 旧文件 %d 站' % len(old))

    try:
        rows = fetch_rows()
    except Exception as exc:
        print('[fail] 拉取现网失败：%s' % exc)
        return False

    entries = {}
    skipped = []
    for row in rows:
        name = row.get('name')
        if not name:
            continue
        entry, err = build_entry(row, old.get(name))
        if entry is None:
            skipped.append((name, err))
            continue
        entries[name] = entry

    if not entries:
        print('[fail] 现网列表为空，保留旧文件')
        return False

    missing = [n for n, e in entries.items()
               if not e['Receiver'].get('DateInstalled') or not e['Antenna'].get('DateInstalled')]
    print('[info] 需要补设备安装日期的站点 %d 个' % len(missing))
    if missing:
        for site, dates, err in fill_install_dates(missing):
            if not dates:
                continue
            e = entries[site]
            if dates[0] and not e['Receiver'].get('DateInstalled'):
                e['Receiver']['DateInstalled'] = dates[0]
            if dates[1] and not e['Antenna'].get('DateInstalled'):
                e['Antenna']['DateInstalled'] = dates[1]

    added = sorted(set(entries) - set(old))
    removed = sorted(set(old) - set(entries))

    print('[ok] 写入 %d 站：新增 %d，移除（已退役/不在现网）%d'
          % (len(entries), len(added), len(removed)))
    if added:
        print('     新增：' + ', '.join(added[:12]) + (' …' if len(added) > 12 else ''))
    if removed:
        print('     移除：' + ', '.join(removed[:12]) + (' …' if len(removed) > 12 else ''))
    if skipped:
        print('[warn] 缺坐标跳过 %d 个：%s' % (len(skipped), skipped[:6]))

    if dry_run:
        print('[dry-run] 未写入文件')
        return True

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print('[ok] 已写入 %s（%.1f KB）' % (path, os.path.getsize(path) / 1024))
    return True


def main():
    refresh(DATA_PATH, dry_run='--dry-run' in sys.argv)
