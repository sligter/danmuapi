import requests
import hashlib
import uuid
import json
import time
import os
import csv
from datetime import datetime
import urllib.parse
from tqdm import tqdm

class MgtvVideoScraper:
    """芒果TV视频信息获取类"""
    def __init__(self, base_dir="danmu_data"):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.mgtv.com/",
        }
        self.api_video_info = "https://pcweb.api.mgtv.com/video/info"
        self.api_danmaku = "https://galaxy.bz.mgtv.com/rdbarrage"
        
        # 创建保存目录
        self.save_dir = os.path.join(base_dir, "mgtv")
        os.makedirs(self.save_dir, exist_ok=True)

    def get_video_list(self, keyword):
        """获取视频列表"""
        searcher = MgtvSearch()
        response = searcher.search(keyword)
        videos = []
        
        # 解析搜索结果
        if response and 'data' in response and 'contents' in response['data']:
            for content in response['data']['contents']:
                if content.get('type') == 'program' or content.get('type') == 'serial':
                    data = content.get('data', {})
                    # 优先获取节目ID
                    video_id = data.get('uuid', '')
                    title = data.get('title', '未知标题')
                    
                    # 如果没有直接的uuid，尝试从rpt中提取
                    if not video_id and 'id=' in data.get('rpt', ''):
                        rpt = data.get('rpt', '')
                        video_id = rpt.split('id=')[1].split('&')[0]
                    
                    # 如果有sourceList，获取第一个source的vid
                    if not video_id and data.get('sourceList'):
                        for source in data.get('sourceList', []):
                            if source.get('vid'):
                                video_id = source.get('vid')
                                break
                    
                    if video_id:
                        videos.append({
                            'title': title,
                            'vid': video_id
                        })
                        
                    # 尝试处理年份列表（适用于部分剧集）
                    year_list = data.get('yearList', [])
                    for year_item in year_list:
                        if 'title' in year_item:
                            year_title = year_item.get('title', '')
                            if year_title:
                                # 避免重复添加
                                if not any(v['title'] == year_title for v in videos):
                                    videos.append({
                                        'title': year_title,
                                        'vid': video_id
                                    })
        
        # 如果没有找到视频，尝试更直接的方法提取结果
        if not videos and response and 'data' in response:
            # 处理可能存在的内容列表
            for content_type in ['contents', 'listItems']:
                if content_type in response['data']:
                    for content in response['data'][content_type]:
                        # 检查是否有数据字段
                        if 'data' in content:
                            data = content.get('data', {})
                            video_id = data.get('uuid', '')
                            title = data.get('title', '未知标题')
                            
                            # 尝试从不同的字段提取id
                            if not video_id and 'id=' in data.get('rpt', ''):
                                rpt = data.get('rpt', '')
                                video_id = rpt.split('id=')[1].split('&')[0]
                            
                            # 添加找到的视频
                            if video_id and title:
                                videos.append({
                                    'title': title,
                                    'vid': video_id
                                })
        
        return videos, response

    def get_video_info(self, response, v_uuid):
        """获取视频集数信息"""
        episodes = []
        base_url = "https://www.mgtv.com"
        
        # 查找匹配的节目
        if response and 'data' in response and 'contents' in response['data']:
            for content in response['data']['contents']:
                if content.get('type') == 'program' or content.get('type') == 'serial':
                    data = content.get('data', {})
                    year_list = data.get('yearList', [])
                    
                    # 从rpt中提取id
                    program_id = ''
                    rpt = data.get('rpt', '')
                    if 'id=' in rpt:
                        program_id = rpt.split('id=')[1].split('&')[0]
                    else:
                        program_id = data.get('uuid', '')
                    
                    # 如果找到匹配的节目
                    if program_id == v_uuid or data.get('uuid') == v_uuid:
                        # 优先处理sourceList
                        source_list = []
                        # 直接处理data中的sourceList
                        if 'sourceList' in data:
                            source_list = data.get('sourceList', [])
                        # 如果year_list中有sourceList，也要处理
                        for year_item in year_list:
                            if 'sourceList' in year_item:
                                source_list.extend(year_item.get('sourceList', []))
                        
                        # 遍历所有数据源
                        for source in source_list:
                            # 获取第一页集数
                            video_list = source.get('videoList', [])
                            for video in video_list:
                                url = video.get('url', '')
                                if url:
                                    episodes.append({
                                        'title': video.get('title', '未知集数'),
                                        'url': f"{base_url}{url.lstrip('/')}"
                                    })
                            
                            # 如果有更多页，继续获取
                            if source.get('hasMore') and source.get('moreUrl'):
                                try:
                                    # 从moreUrl提取重要参数
                                    more_url = source.get('moreUrl')
                                    api_params = {}
                                    
                                    # 解析moreUrl中的参数
                                    if '?' in more_url:
                                        path, query = more_url.split('?', 1)
                                        for param in query.split('&'):
                                            if '=' in param:
                                                key, value = param.split('=', 1)
                                                api_params[key] = value
                                    
                                    # 添加必需的额外参数
                                    api_params['src'] = 'mgtv'
                                    api_params['allowedRC'] = '1'
                                    api_params['_support'] = '10000000'
                                    
                                    # 构建请求URL
                                    api_url = f"https://mobileso.bz.mgtv.com/pc/videos/v1"
                                    
                                    print(f"获取更多集数：{api_url}")
                                    print(f"参数：{api_params}")
                                    
                                    # 请求下一页数据
                                    response = self.session.get(api_url, params=api_params, headers=self.headers)
                                    
                                    # 检查响应状态
                                    if response.status_code != 200:
                                        print(f"请求失败，状态码: {response.status_code}")
                                        continue
                                    
                                    # 解析JSON数据
                                    try:
                                        more_data = response.json()
                                    except Exception as e:
                                        print(f"解析JSON数据出错: {e}")
                                        print(f"响应内容: {response.text[:200]}")  # 打印部分响应内容进行调试
                                        continue
                                    
                                    # 处理下一页数据
                                    if more_data.get('code') == 200 and 'data' in more_data:
                                        data = more_data.get('data', {})
                                        # 获取集数
                                        for video in data.get('videoList', []):
                                            url = video.get('url', '')
                                            if url:
                                                episodes.append({
                                                    'title': video.get('title', '未知集数'),
                                                    'url': f"{base_url}{url.lstrip('/')}"
                                                })
                                except Exception as e:
                                    print(f"获取更多集数时出错: {e}")
                        # 只处理第一个匹配的节目
                        break
        
        # 如果没有找到集数，尝试直接从响应中提取视频数据
        if not episodes and response and 'data' in response:
            # 遍历contents寻找视频列表
            contents = response['data'].get('contents', [])
            for content in contents:
                if content.get('type') == 'program' or content.get('type') == 'serial':
                    data = content.get('data', {})
                    # 检查是否与请求的vid匹配
                    if data.get('uuid') == v_uuid or ('rpt' in data and 'id=' in data['rpt'] and data['rpt'].split('id=')[1].split('&')[0] == v_uuid):
                        # 尝试直接获取sourceList中的视频
                        for source in data.get('sourceList', []):
                            for video in source.get('videoList', []):
                                url = video.get('url', '')
                                if url:
                                    episodes.append({
                                        'title': video.get('title', '未知集数'),
                                        'url': f"{base_url}{url.lstrip('/')}"
                                    })
        
        return episodes

    def fetch_danmu(self, url, title):
        """获取视频弹幕"""
        try:
            # 从URL中提取cid和vid
            _u = url.split(".")[-2].split("/")
            cid = _u[-2]
            vid = _u[-1]
            
            # 获取视频信息
            params = {'cid': cid, 'vid': vid}
            res = self.session.get(self.api_video_info, params=params, headers=self.headers)
            video_info = res.json()
            
            # 获取视频时长
            _time = video_info.get("data", {}).get("info", {}).get("time", "00:00:00")
            end_time = self._time_to_second(_time.split(":"))
            
            # 分段获取弹幕
            danmu_list = []
            for _t in tqdm(range(0, end_time, 60 * 1000), desc="获取弹幕中"):
                response = self.session.get(
                    self.api_danmaku,
                    params={'vid': vid, "cid": cid, "time": _t},
                    headers=self.headers
                )
                data = response.json()
                if data.get("data", {}).get("items"):
                    for item in data["data"]["items"]:
                        danmu_list.append([
                            item.get('time', 0),  # 时间戳
                            item.get('color', 16777215),  # 颜色
                            item.get('content', '')  # 内容
                        ])
            
            # 保存弹幕
            return self._save_danmu(danmu_list, title)
            
        except Exception as e:
            print(f"获取弹幕出错: {e}")
            return None

    def _time_to_second(self, time_parts):
        """将时间转换为毫秒数"""
        if len(time_parts) == 3:  # HH:MM:SS
            return int(time_parts[0]) * 3600 * 1000 + int(time_parts[1]) * 60 * 1000 + int(time_parts[2]) * 1000
        elif len(time_parts) == 2:  # MM:SS
            return int(time_parts[0]) * 60 * 1000 + int(time_parts[1]) * 1000
        return 0

    def _save_danmu(self, danmu_list, title):
        """保存弹幕到CSV文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{title}_{timestamp}.csv"
        filepath = os.path.join(self.save_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, escapechar='\\', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['time', 'color', 'content'])  # 写入表头
            writer.writerows(danmu_list)
            
        print(f"\n--- 弹幕保存到文件 {filepath} ---")
        print("--- 完成 ---")
        return filepath

class MgtvSearch:
    """芒果TV搜索类"""
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://so.mgtv.com/",
            "Origin": "https://so.mgtv.com"
        }
        self.sign_key = "xHAa3YZflWLogZUOzl"
        self.device_id = str(uuid.uuid4()).replace("-", "")

    def search(self, keyword, page=1, page_size=10):
        """搜索视频"""
        params = {
            'allowedRC': '1',
            'src': 'mgtv',
            'did': self.device_id,
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'signVersion': '1',
            'signNonce': uuid.uuid4().hex,
            'q': keyword,
            'pn': str(page),
            'pc': str(page_size),
            'uid': '',
            'corr': '1',
            '_support': '10000000'
        }
        
        params['signature'] = self._generate_signature(params)
        
        try:
            response = self.session.get(
                "https://mobileso.bz.mgtv.com/pc/search/v2",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            print(response.json())
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"搜索请求失败: {str(e)}")

    def _generate_signature(self, params):
        """生成签名"""
        filtered_params = {
            k: self._encodeURI(str(v)) for k, v in params.items() 
            if v is not None and str(v).strip()
        }
        
        sorted_params = sorted(filtered_params.items(), key=lambda x: x[0])
        param_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
        sign_string = f"{self.sign_key}{param_string}{self.sign_key}"
        
        return hashlib.md5(sign_string.encode()).hexdigest()

    def _encodeURI(self, s):
        """模拟 JS 的 encodeURI 函数"""
        return urllib.parse.quote(str(s), safe='~@#$&()*!+=:;,.?/\'')

def main():
    """测试函数"""
    scraper = MgtvVideoScraper()
    
    # 搜索视频
    videos, response = scraper.get_video_list("小巷人家")
    if not videos:
        print("没有找到视频，尝试从原始数据中提取视频信息...")
        # 尝试直接从原始数据中提取视频信息
        if response and 'data' in response:
            contents = response['data'].get('contents', [])
            for idx, content in enumerate(contents):
                if 'data' in content:
                    data = content.get('data', {})
                    title = data.get('title', f'未知视频 {idx+1}')
                    rpt = data.get('rpt', '')
                    video_id = ''
                    
                    # 尝试从rpt中提取id
                    if 'id=' in rpt:
                        video_id = rpt.split('id=')[1].split('&')[0]
                    elif 'uuid' in data:
                        video_id = data.get('uuid', '')
                    
                    if video_id:
                        videos.append({
                            'title': title,
                            'vid': video_id
                        })
        
        if not videos:
            print("仍然没有找到视频，退出程序")
            return
    
    # 打印搜索结果
    for i, video in enumerate(videos):
        print(f"{i+1}. {video['title']} - {video['vid']}")
    
    # 获取集数列表
    selected = int(input("选择一个视频 (输入序号): ")) - 1
    if 0 <= selected < len(videos):
        episodes = scraper.get_video_info(response, videos[selected]['vid'])
        
        # 如果没有找到集数，尝试直接获取列表
        if not episodes and response and 'data' in response:
            print("尝试使用其他方法获取集数列表...")
            # 直接遍历视频列表寻找集数
            for content in response['data'].get('contents', []):
                if 'data' in content:
                    data = content.get('data', {})
                    # 获取匹配的视频信息
                    if (data.get('uuid') == videos[selected]['vid'] or 
                        ('rpt' in data and 'id=' in data['rpt'] and data['rpt'].split('id=')[1].split('&')[0] == videos[selected]['vid'])):
                        # 遍历所有来源
                        for source in data.get('sourceList', []):
                            for video in source.get('videoList', []):
                                url = video.get('url', '')
                                if url:
                                    if not url.startswith('http'):
                                        url = f"https://www.mgtv.com{url.lstrip('/')}"
                                    episodes.append({
                                        'title': video.get('title', '未知集数'),
                                        'url': url
                                    })
        
        if not episodes:
            print("没有找到集数")
            return
        
        # 打印集数列表
        for i, episode in enumerate(episodes):
            print(f"{i+1}. {episode['title']}")
        
        # 下载弹幕
        ep_selected = int(input("选择一集 (输入序号): ")) - 1
        if 0 <= ep_selected < len(episodes):
            filepath = scraper.fetch_danmu(
                episodes[ep_selected]['url'], 
                f"{videos[selected]['title']}_{episodes[ep_selected]['title']}"
            )
            if filepath:
                print(f"弹幕已保存到: {filepath}")
    
if __name__ == "__main__":
    main() 