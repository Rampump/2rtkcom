import socket
import json
import configparser
import os
import sys
import base64
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import requests

def load_config(config_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """从配置文件加载NTRIP服务器信息

    配置路径优先级：显式传入 > 环境变量 NTRIP_CONFIG > 默认 ntrip_servers.ini
    本地/服务器用默认文件（含私有凭据，不入库）；
    GitHub Actions 用 ntrip_servers.ci.ini（仅公开源）。
    """
    if config_path is None:
        config_path = os.environ.get('NTRIP_CONFIG', 'ntrip_servers.ini')

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    config = configparser.ConfigParser()
    config.read(config_path)
    
    servers = []
    for section in config.sections():
        if config.getboolean(section, 'enabled', fallback=True):
            servers.append({
                'name': section,
                'host': config.get(section, 'host'),
                'port': config.getint(section, 'port', fallback=2101),
                'username': config.get(section, 'username', fallback=None),
                'password': config.get(section, 'password', fallback=None),
                'output_prefix': config.get(section, 'output_prefix', fallback=section),
                'address': config.get(section, 'address', fallback=None)
            })
    
    if not servers:
        raise ValueError("配置文件中未找到启用的服务器")
    
    return servers

def fetch_mountpoints(server: Dict[str, Any]) -> Tuple[bool, str]:
    """从指定NTRIP服务器获取挂载点信息，优先使用标准NTRIP协议，失败后尝试URL方式"""
    host = server['host']
    port = server['port']
    name = server['name']
    output_prefix = server['output_prefix']
    username = server.get('username')
    password = server.get('password')
    
    print(f"正在处理服务器: {name} ({host}:{port})")
    
    # 创建目录用于存储数据
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    # 优先尝试标准NTRIP协议
    success, message, response_text = try_ntrip_protocol(host, port, username, password)
    
    if not success:
        print(f"NTRIP协议方式失败，尝试URL方式: {message}")
        # 尝试URL方式
        success, message, response_text = try_url_method(host, port)
    
    if not success:
        return False, message
    
    try:
        # 保存原始数据
        txt_path = os.path.join(data_dir, f"{output_prefix}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(response_text)
        
        # 解析数据，同时将服务器信息添加到每个挂载点
        mountpoints = parse_mountpoint_data(response_text, server)
        
        # 保存JSON
        json_path = os.path.join(data_dir, f"{output_prefix}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(mountpoints, f, ensure_ascii=False, indent=4)
        
        return True, f"成功处理 {len(mountpoints)} 个挂载点"
    
    except Exception as e:
        return False, f"处理失败: {str(e)}"

def try_ntrip_protocol(host: str, port: int, username: Optional[str], password: Optional[str]) -> Tuple[bool, str, str]:
    """尝试使用标准NTRIP协议获取挂载点信息"""
    try:
        # 构建NTRIP请求
        request = f"GET / HTTP/1.0\r\n"
        request += f"User-Agent: Python-NTRIP-Client\r\n"
        request += f"Accept: */*\r\n"
        request += f"Connection: close\r\n"
        
        # 添加认证信息（如果有）
        if username and password:
            auth_string = f"{username}:{password}".encode('ascii')
            auth_header = base64.b64encode(auth_string).decode('ascii')
            request += f"Authorization: Basic {auth_header}\r\n"
        
        request += "\r\n"
        
        # 建立TCP连接
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(30)
            s.connect((host, port))
            s.sendall(request.encode('ascii'))
            
            # 接收数据
            response = b""
            while True:
                data = s.recv(4096)
                if not data:
                    break
                response += data
        
        # 转换为字符串
        response_text = response.decode('ascii', errors='replace')
        
        # 检查是否成功获取数据：必须是 HTTP 200 且包含源表
        status_ok = " 200 " in response_text[:64]
        if status_ok and "SOURCETABLE" in response_text:
            return True, "NTRIP协议方式成功", response_text
        else:
            if not status_ok:
                return False, f"HTTP状态异常: {response_text.splitlines()[0] if response_text else '无响应'}", response_text
            return False, "未收到有效的源表响应", response_text
    
    except Exception as e:
        return False, f"NTRIP协议异常: {str(e)}", ""

def try_url_method(host: str, port: int) -> Tuple[bool, str, str]:
    """尝试使用URL方式获取挂载点信息"""
    try:
        headers = {
            'Ntrip-Version': 'Ntrip/2.0',
            'User-Agent': 'Python-NTRIP-Client'
        }
        url = f'http://{host}:{port}/'
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return False, f"URL请求失败，状态码: {response.status_code}", ""
        
        return True, "URL方式成功", response.text
    
    except requests.RequestException as e:
        return False, f"URL请求异常: {str(e)}", ""
    except Exception as e:
        return False, f"URL处理失败: {str(e)}", ""

def parse_mountpoint_data(content: str, server_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析NTRIP服务器返回的挂载点数据，并添加服务器连接信息"""
    mountpoints = []
    lines = content.strip().split('\n')
    
    # 从服务器信息中提取需要添加的数据
    server_host = server_info['host']
    server_port = server_info['port']
    server_address = server_info.get('address')
    server_username = server_info.get('username')
    server_password = server_info.get('password')
    
    for line in lines:
        if not line.startswith('STR;'):
            continue
            
        parts = line.strip(';').split(';')
        if len(parts) < 12:  # 确保数据完整性
            continue
            
        try:
            # 解析经纬度
            lat = float(parts[9])
            lon = float(parts[10])
            
            # 创建挂载点信息，包含原始数据和服务器连接信息
            mountpoint = {
                'name': parts[1],
                'format': parts[3],
                'rtcm_types': parts[4].split(',') if len(parts) > 4 else [],
                'systems': parts[6] if len(parts) > 6 else '',
                'country': parts[8] if len(parts) > 8 else '',
                'latitude': lat,
                'longitude': lon,
                'height': float(parts[11]) if parts[11].strip() else None,
                'network': parts[7] if len(parts) > 7 else '',
                'ntrip_version': parts[13] if len(parts) > 13 else '',
                # 添加服务器连接信息
                'server_host': server_host,
                'server_port': server_port,
                'registration_address': server_address,
                'username': server_username,
                'password': server_password
            }
            
            mountpoints.append(mountpoint)
        except (ValueError, IndexError) as e:
            print(f"警告: 解析挂载点 {parts[1]} 失败: {str(e)}")
    
    return mountpoints

def download_igs_network():
    """刷新 IGS 现网站点表 data/IGSNetwork.json

    优先走 network.igs.org 的公共 API（scripts/fetch_igs.py）：只取现网 535 站，
    还带城市/州、所属网络、运营机构、DOMES、实时系统等字段。
    接口不可用时退回 files.igs.org 的官方站志汇总，同样是现网列表。

    注意：不能再拉 IGSNetworkWithFormer.json —— 那份含 241 个已退役站点，
    前端点进去官方接口一律 404，只能显示"已不在 IGS 现网"。
    """
    output_dir = "data"
    output_file = os.path.join(output_dir, "IGSNetwork.json")
    os.makedirs(output_dir, exist_ok=True)

    print("正在刷新IGS现网站点表...")

    # 1) 公共 API
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import fetch_igs
        if fetch_igs.refresh(output_file):
            print(f"IGS站点表已刷新（API）-> {output_file}")
            return True
        print("API 刷新未成功，尝试退回 files.igs.org 站志")
    except Exception as e:
        print(f"API 刷新异常: {e}，尝试退回 files.igs.org 站志")

    # 2) 官方站志汇总（无 former 版）
    url = "https://files.igs.org/pub/station/general/IGSNetwork.json"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise Exception(f"请求失败，状态码: {response.status_code}")

        payload = response.json()
        if not payload:
            raise Exception("站志内容为空")

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')

        print(f"IGS站点表已刷新（files.igs.org，{len(payload)} 站）-> {output_file}")
        return True
    except requests.RequestException as e:
        print(f"下载失败: {str(e)}")
        return False
    except Exception as e:
        print(f"处理失败: {str(e)}")
        return False

def write_meta(results: List[Dict[str, Any]], igs_ok: bool) -> str:
    """采集完成后，将各数据源的抓取结果写入 data/meta.json，供 Web 端展示更新时间与状态"""
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
    
    meta = {
        'last_update': now,
        'igs_network': {'ok': igs_ok, 'file': 'IGSNetwork.json'},
        'sources': results
    }
    
    meta_path = os.path.join(data_dir, "meta.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    print(f"元数据已写入 {meta_path}")
    return meta_path

def main():
    """主函数：抓取所有启用的 NTRIP 服务器，汇总结果并写入 meta.json"""
    try:
        servers = load_config()
    except Exception as e:
        print(f"配置错误: {str(e)}")
        print("\n请创建配置文件 ntrip_servers.ini，格式如下:")
        print("""[rtk2go]
host = rtk2go.com
port = 2101
enabled = true
output_prefix = rtk2go
username = mail
password = none
address = https://www.rtk2go.com/

[France]
host = crtk.net
port = 2101
enabled = true
output_prefix = France
address = https://map.centipede-rtk.org/
username = centipede
password = centipede""")
        return
    
    print(f"发现 {len(servers)} 个已启用的NTRIP服务器配置")
    
    # 下载IGS网络信息
    igs_ok = download_igs_network()
    
    # 抓取所有服务器，记录每个源的结果
    results = []
    for server in servers:
        success, message = fetch_mountpoints(server)
        status = "✓ 成功" if success else "✗ 失败"
        print(f"[{status}] {server['name']}: {message}")
        
        # 记录每个源的状态与站点数
        count = 0
        if success:
            json_path = os.path.join("data", f"{server['output_prefix']}.json")
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    count = len(json.load(f))
            except Exception:
                count = 0
        
        results.append({
            'name': server['name'],
            'file': f"{server['output_prefix']}.json",
            'ok': success,
            'station_count': count,
            'message': message,
            # 本轮失败时，上一次的 successful 文件被保留下来充当备用数据
            'stale': not success,
        })
    
    # 写入元数据
    write_meta(results, igs_ok)
    print(f"\n采集完成：{sum(1 for r in results if r['ok'])}/{len(results)} 个数据源成功")

if __name__ == "__main__":
    main()