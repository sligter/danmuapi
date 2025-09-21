import requests
import time
import hashlib
import random
import string
import json
import re
import csv
import os
from datetime import datetime
from tqdm import tqdm

class BilibiliVideoScraper:
    def __init__(self, base_dir="danmu_data"):
        self.base_dir = base_dir
        self.data_list = []
        self.api_video_info = "https://api.bilibili.com/x/web-interface/view"
        self.api_epid_cid = "https://api.bilibili.com/pgc/view/web/season"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 确保下载目录存在
        self.danmu_dir = os.path.join(base_dir, "bilibili")
        os.makedirs(self.danmu_dir, exist_ok=True)

    def request_data(self, method, url, **kwargs):
        """发送HTTP请求"""
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response
        except requests.RequestException as e:
            print(f"请求失败: {e}")
            return None

    def parse_danmaku(self, xml_data):
        """解析XML格式的弹幕数据"""
        self.data_list = []
        try:
            if isinstance(xml_data, bytes):
                xml_data = xml_data.decode('utf-8')
            
            data_list = re.findall('<d p="(.*?)">(.*?)<\/d>', xml_data)
            for data in tqdm(data_list, desc="解析弹幕"):
                try:
                    data_time = data[0].split(",")
                    self.data_list.append({
                        "timepoint": int(float(data_time[0]) * 1000),
                        "ct": data_time[1],
                        "content": data[1].encode('utf-8').decode('utf-8')
                    })
                except UnicodeError:
                    continue
                
            self.data_list.sort(key=lambda x: x['timepoint'])
            return self.data_list
            
        except Exception as e:
            print(f"解析弹幕时出错: {e}")
            return []

    def save_to_csv(self, data_list, filename):
        """保存弹幕数据到CSV文件"""
        if not data_list:
            print("没有数据可保存")
            return None
            
        filepath = os.path.join(self.danmu_dir, filename)
        fieldnames = ['timepoint', 'ct', 'content']
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for item in data_list:
                    row = {k: str(v) for k, v in item.items()}
                    writer.writerow(row)
            print(f"弹幕已保存到: {filepath}")
            return filepath
        except Exception as e:
            print(f"保存文件失败: {e}")
            return None

    def get_video_list(self, keyword):
        """搜索视频列表"""
        results = []
        try:
            params = {
                "__refresh__": "true",
                "_extra": "",
                "context": "",
                "page": 1,
                "page_size": 42,
                "from_source": "",
                "platform": "pc",
                "highlight": 1,
                "single_column": 0,
                "keyword": keyword,
                "qv_id": self._generate_qv_id(),
                "w_rid": hashlib.md5(str(time.time()).encode()).hexdigest(),
                "wts": int(time.time())
            }
            
            response = requests.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/all/v2",
                params=params,
                headers=self._get_search_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # 处理番剧搜索结果
                    for item in data.get("data", {}).get("result", []):
                        # 处理番剧类型 (番剧)
                        if item.get("result_type") == "media_bangumi":
                            for media in item.get("data", []):
                                results.append({
                                    "title": media.get("title", "").replace('<em class="keyword">', '').replace('</em>', ''),
                                    "id": media.get("season_id", ""),
                                    "pageUrl": f"https://www.bilibili.com/bangumi/play/ss{media.get('season_id', '')}"
                                })
                        
                        # 处理番剧类型 (电影/纪录片)
                        elif item.get("result_type") == "media_ft":
                            for media in item.get("data", []):
                                results.append({
                                    "title": media.get("title", "").replace('<em class="keyword">', '').replace('</em>', ''),
                                    "id": media.get("season_id", ""),
                                    "pageUrl": f"https://www.bilibili.com/bangumi/play/ss{media.get('season_id', '')}"
                                })
                        
                        # 处理普通视频
                        elif item.get("result_type") == "video":
                            for video in item.get("data", []):
                                results.append({
                                    "title": video.get("title", "").replace('<em class="keyword">', '').replace('</em>', ''),
                                    "id": video.get("aid", ""),
                                    "bvid": video.get("bvid", ""),
                                    "pageUrl": video.get("arcurl", "")
                                })
            
            return results, data
        except Exception as e:
            print(f"搜索视频失败: {e}")
            return [], None

    def get_video_info(self, data, video_id):
        """获取视频信息和剧集列表"""
        episodes = []
        try:
            for item in data.get("data", {}).get("result", []):
                # 处理番剧类型
                if item.get("result_type") in ["media_bangumi", "media_ft"]:
                    for media in item.get("data", []):
                        if str(media.get("season_id")) == str(video_id):
                            for ep in media.get("eps", []):
                                episodes.append({
                                    "title": ep.get("index_title", "") + " " + ep.get("long_title", ""),
                                    "playUrl": ep.get("url", ""),
                                    "duration": 0  # B站API中可能没有直接提供时长
                                })
                            break
                
                # 处理普通视频类型
                elif item.get("result_type") == "video":
                    for video in item.get("data", []):
                        if str(video.get("aid")) == str(video_id) or video.get("bvid") == str(video_id):
                            episodes.append({
                                "title": video.get("title", "").replace('<em class="keyword">', '').replace('</em>', ''),
                                "playUrl": video.get("arcurl", ""),
                                "duration": video.get("duration", "0")
                            })
                            break
            
            return episodes
        except Exception as e:
            print(f"获取视频信息失败: {e}")
            return []

    def fetch_danmu(self, url, title=None):
        """获取弹幕数据"""
        try:
            # 判断链接类型
            if "bangumi/play/ep" in url:
                # 从URL中提取epid
                epid = url.split('?')[0].split('/')[-1]
                if not epid.startswith('ep'):
                    print("无效的URL格式")
                    return None
                    
                params = {"ep_id": epid[2:]}
                res = self.request_data("GET", self.api_epid_cid, params=params)
                if not res:
                    return None
                    
                res_json = res.json()
                if res_json.get("code") != 0:
                    print("获取番剧信息失败")
                    return None
                    
                # 获取cid并下载弹幕
                for episode in res_json.get("result", {}).get("episodes", []):
                    if episode.get("id", 0) == int(epid[2:]):
                        xml_res = self.request_data("GET", f'https://comment.bilibili.com/{episode.get("cid")}.xml')
                        if not xml_res:
                            return None
                            
                        danmu_list = self.parse_danmaku(xml_res.text)
                        if not danmu_list:
                            return None
                            
                        # 生成文件名
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{title or 'bilibili'}_{timestamp}.csv"
                        
                        # 保存弹幕
                        return self.save_to_csv(danmu_list, filename)
                        
                print("未找到对应剧集")
                return None
            
            # 普通视频
            elif "video/BV" in url or "video/av" in url:
                bvid = None
                aid = None
                
                if "video/BV" in url:
                    # 提取BV号
                    bvid = url.split('?')[0].split('/')[-1]
                    params = {"bvid": bvid}
                else:
                    # 提取av号
                    aid = url.split('?')[0].split('/')[-1]
                    if aid.startswith('av'):
                        aid = aid[2:]
                    params = {"aid": aid}
                
                # 获取视频信息
                res = self.request_data("GET", self.api_video_info, params=params)
                if not res:
                    return None
                
                res_json = res.json()
                if res_json.get("code") != 0:
                    print("获取视频信息失败")
                    return None
                
                # 获取cid并下载弹幕
                cid = res_json.get("data", {}).get("cid")
                if not cid:
                    print("未找到视频cid")
                    return None
                
                xml_res = self.request_data("GET", f'https://comment.bilibili.com/{cid}.xml')
                if not xml_res:
                    return None
                
                danmu_list = self.parse_danmaku(xml_res.text)
                if not danmu_list:
                    return None
                
                # 生成文件名
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{title or 'bilibili'}_{timestamp}.csv"
                
                # 保存弹幕
                return self.save_to_csv(danmu_list, filename)
            
            else:
                print("不支持的URL格式")
                return None
            
        except Exception as e:
            print(f"获取弹幕失败: {e}")
            return None

    def _generate_qv_id(self):
        """生成搜索请求用的qv_id"""
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))

    def _get_search_headers(self):
        """获取搜索请求的headers"""
        cookie = self._generate_random_cookie()
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cookie": cookie,
            "Origin": "https://www.bilibili.com",
            "Referer": "https://www.bilibili.com/"
        }

    def _generate_random_cookie(self):
        """生成随机cookie"""
        buvid3 = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        b_nut = ''.join(random.choice(string.digits) for _ in range(10))
        buvid4 = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        return f"buvid3={buvid3}; b_nut={b_nut}; buvid4={buvid4}" 
    
if __name__ == "__main__":
    scraper = BilibiliVideoScraper()
    keyword = "鬼灭之刃"
    videos, data = scraper.get_video_list(keyword)
    episode_list = scraper.get_video_info(data, "47836")
    print(videos)
    print(data)
    print(episode_list)

