import requests
import re
import os
import sys # 用于 sys.exit()

# --- Cloudflare 配置与设置 ---
print("开始运行脚本：Cloudflare IP 更新器")

CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_ZONE_ID = os.getenv('CLOUDFLARE_ZONE_ID')

if not CLOUDFLARE_API_TOKEN:
    print("错误：CLOUDFLARE_API_TOKEN 环境变量未设置。")
    sys.exit(1)
if not CLOUDFLARE_ZONE_ID:
    print("错误：CLOUDFLARE_ZONE_ID 环境变量未设置。")
    sys.exit(1)

BASE_DOMAIN_NAME = "lyl7410.cloudns.ch"
TARGET_SUBDOMAINS = [f"sp{i}.{BASE_DOMAIN_NAME}" for i in range(10, 21)] # sp10 到 sp20

CLOUDFLARE_HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}

print("Cloudflare 配置已加载。")
print(f"Zone ID: {CLOUDFLARE_ZONE_ID}")
print(f"基础域名: {BASE_DOMAIN_NAME}")
print(f"目标子域名: {TARGET_SUBDOMAINS}")

# --- 现有 IP 收集逻辑 ---
# 目标URL列表
urls = [
    'https://cf.vvhan.com/',
    'https://ip.164746.xyz'
]
ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
all_ips = []

print("开始 IP 收集阶段...")
for url in urls:
    print(f"正在从以下地址获取IP: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        page_content = response.text
        ip_matches = re.findall(ip_pattern, page_content)
        if ip_matches: # 检查是否找到了任何IP
            for ip in ip_matches:
                print(f"从 {url} 提取到IP: {ip}") # 新增的中文日志信息
                all_ips.append(ip) # 单独添加IP
            print(f"从 {url} 找到 {len(ip_matches)} 个潜在IP。")
        else:
            print(f"未在 {url} 找到IP。")
    except requests.exceptions.RequestException as e:
        print(f"获取 URL {url} 时出错: {e}")
    except Exception as e:
        print(f"处理 {url} 时发生意外错误: {e}")

unique_ips = []
seen_ips = set()
for ip in all_ips:
    if ip not in seen_ips:
        unique_ips.append(ip)
        seen_ips.add(ip)

if os.path.exists('ip.txt'):
    try:
        os.remove('ip.txt')
        print("已删除现有的 ip.txt 文件。")
    except OSError as e:
        print(f"删除现有 ip.txt 文件时出错: {e}")

try:
    with open('ip.txt', 'w') as file:
        for ip in unique_ips:
            file.write(ip + '')
    print(f"{len(unique_ips)} 个唯一IP地址已收集并保存到 ip.txt。")
except IOError as e:
    print(f"写入 ip.txt 文件时出错: {e}")
except Exception as e:
    print(f"写入文件时发生意外错误: {e}")

# --- Cloudflare DNS 更新逻辑 ---
print("开始 Cloudflare DNS 更新阶段...")

if not unique_ips:
    print("未收集到唯一IP。跳过 DNS 更新过程。")
else:
    print(f"找到 {len(unique_ips)} 个唯一IP。将为最多 {len(TARGET_SUBDOMAINS)} 个子域名更新DNS。")
    
    num_ips_to_process = min(len(unique_ips), len(TARGET_SUBDOMAINS))

    for i in range(num_ips_to_process):
        current_subdomain = TARGET_SUBDOMAINS[i]
        ip_to_assign = unique_ips[i]
        record_id = None # 为每个子域名重置

        print(f"正在处理子域名: {current_subdomain}，IP为: {ip_to_assign}")

        # 获取现有 DNS 记录
        fetch_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records?type=A&name={current_subdomain}"
        print(f"尝试获取 {current_subdomain} 的现有 DNS 记录...")
        try:
            response = requests.get(fetch_url, headers=CLOUDFLARE_HEADERS, timeout=10)
            if response.status_code == 404:
                print(f"未找到 {current_subdomain} 的现有 'A' 记录 (404)。将尝试创建。")
                record_id = None
            elif response.status_code == 401 or response.status_code == 403:
                print(f"获取 {current_subdomain} 的 DNS 记录时出现授权错误 ({response.status_code})。请检查 API 令牌和权限。跳过此子域名。")
                print(f"响应: {response.text}")
                continue
            else:
                response.raise_for_status()
                records_data = response.json()
                if records_data.get("success") and records_data.get("result"):
                    if records_data["result"]:
                        record_id = records_data["result"][0]["id"]
                        print(f"找到 {current_subdomain} 的现有记录，ID: {record_id}")
                    else:
                        print(f"未找到 {current_subdomain} 的现有 'A' 记录 (API 调用成功，但结果为空)。")
                        record_id = None
                else:
                    print(f"未能获取 {current_subdomain} 的有效记录数据。响应: {records_data}")
                    record_id = None

        except requests.exceptions.HTTPError as e:
            print(f"获取 {current_subdomain} DNS 记录时发生 HTTP 错误: {e}")
            if record_id is not None:
                print("由于获取过程中发生 HTTP 错误，将在没有有效 record_id 的情况下继续。")
                record_id = None
        except requests.exceptions.RequestException as e:
            print(f"获取 {current_subdomain} DNS 记录时发生网络错误: {e}")
            continue
        except ValueError as e: # 包括 JSONDecodeError
            print(f"解析 {current_subdomain} 的 JSON 响应时出错: {e}")
            record_id = None


        # DNS 更新/创建所需数据
        dns_payload = {
            "type": "A",
            "name": current_subdomain,
            "content": ip_to_assign,
            "ttl": 3600,
            "proxied": False
        }

        if record_id:
            # 更新现有记录
            update_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records/{record_id}"
            print(f"尝试使用IP {ip_to_assign} 更新 {current_subdomain} (ID: {record_id}) 的记录...")
            try:
                response = requests.put(update_url, json=dns_payload, headers=CLOUDFLARE_HEADERS, timeout=10)
                response.raise_for_status()
                update_result = response.json()
                if update_result.get("success"):
                    print(f"已成功将 {current_subdomain} 的 DNS 记录更新为 {ip_to_assign}。")
                else:
                    print(f"未能更新 {current_subdomain} 的 DNS 记录。响应: {update_result}")
            except requests.exceptions.RequestException as e:
                print(f"更新 {current_subdomain} DNS 记录时出错: {e}")
            except ValueError as e:
                print(f"更新 {current_subdomain} 期间解析 JSON 响应时出错: {e}")
        else:
            # 创建新记录
            create_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"
            print(f"尝试为 {current_subdomain} 创建新记录，IP 为: {ip_to_assign}...")
            try:
                response = requests.post(create_url, json=dns_payload, headers=CLOUDFLARE_HEADERS, timeout=10)
                response.raise_for_status()
                create_result = response.json()
                if create_result.get("success"):
                    print(f"已成功为 {current_subdomain} 创建 DNS 记录，IP 为 {ip_to_assign}。")
                else:
                    print(f"未能为 {current_subdomain} 创建 DNS 记录。响应: {create_result}")
            except requests.exceptions.RequestException as e:
                print(f"为 {current_subdomain} 创建 DNS 记录时出错: {e}")
            except ValueError as e:
                print(f"为 {current_subdomain} 创建记录期间解析 JSON 响应时出错: {e}")
    
    print("Cloudflare DNS 更新阶段已完成。")

print("脚本运行结束。")
