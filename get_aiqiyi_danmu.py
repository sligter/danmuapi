import os
import requests
import json
import pandas as pd
from datetime import datetime
import brotli
from math import ceil
import hashlib
from google.protobuf import descriptor_pool, message_factory, descriptor_pb2

class AiqiyiVideoScraper:
    """
    A class for scraping video lists, video details, and fetching danmu (comments) from Aiqiyi Video.
    """

    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self._init_protobuf()

    def _init_protobuf(self):
        """Initialize protobuf message types for danmu parsing"""
        pool = descriptor_pool.DescriptorPool()
        pool.Add(descriptor_pb2.FileDescriptorProto(
            name='danmu.proto',
            package='danmu',
            message_type=[
                descriptor_pb2.DescriptorProto(
                    name='UserInfo',
                    field=[
                        descriptor_pb2.FieldDescriptorProto(
                            name='uid', number=2, type=9, label=1
                        ),
                        descriptor_pb2.FieldDescriptorProto(
                            name='name', number=6, type=9, label=1
                        ),
                    ]
                ),
                descriptor_pb2.DescriptorProto(
                    name='BulletInfo',
                    field=[
                        descriptor_pb2.FieldDescriptorProto(
                            name='content', number=2, type=9, label=1
                        ),
                        descriptor_pb2.FieldDescriptorProto(
                            name='showTime', number=6, type=9, label=1
                        ),
                        descriptor_pb2.FieldDescriptorProto(
                            name='userInfo', number=17, type=11, label=1,
                            type_name='.danmu.UserInfo'
                        ),
                    ]
                ),
                descriptor_pb2.DescriptorProto(
                    name='Entry',
                    field=[
                        descriptor_pb2.FieldDescriptorProto(
                            name='bulletInfo', number=2, type=11, label=3,
                            type_name='.danmu.BulletInfo'
                        ),
                    ]
                ),
                descriptor_pb2.DescriptorProto(
                    name='Danmu',
                    field=[
                        descriptor_pb2.FieldDescriptorProto(
                            name='code', number=1, type=9, label=1
                        ),
                        descriptor_pb2.FieldDescriptorProto(
                            name='entry', number=6, type=11, label=3,
                            type_name='.danmu.Entry'
                        ),
                    ]
                ),
            ]
        ))
        self.DanmuMessage = message_factory.GetMessageClass(pool.FindMessageTypeByName('danmu.Danmu'))

    def get_video_list(self, query):
        """
        Fetch a list of videos matching the query from Aiqiyi.

        Parameters:
        - query (str): The search query.

        Returns:
        - list of dict: List containing video titles and page URLs.
        """
        url = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        params = {
            "key": query,
            "current_page": 1,
            "mode": 1,
            "source": "input",
            "suggest": "",
            "version": "13.034.21537",
            "pageNum": 1,
            "pageSize": 25,
            "pu": "",
            "u": "9e46b0431c96cf2a0a572dac9e6f89c0",
            "scale": 125,
            "token": "",
            "userVip": 0,
            "conduit": "",
            "vipType": -1,
            "os": "",
            "osShortName": "win10",
            "dataType": "",
            "appMode": "",
            "ad": '{"lm":3,"azd":1000000000951,"azt":733,"position":"feed"}',
            "adExt": '{"r":"1.2.1-ares6-pure"}'
        }
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "origin": "https://www.iqiyi.com",
            "referer": "https://www.iqiyi.com/",
            "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Microsoft Edge\";v=\"134\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if 'data' in data and 'templates' in data['data']:
                for template in data['data']['templates']:
                    if 'albumInfo' in template:
                        album_info = template['albumInfo']
                        results.append({
                            'title': album_info.get('title', ''),
                            'playUrl': album_info.get('playUrl', '').split(';')[0].split('=')[1] if album_info.get('playUrl') else '',
                            'qipuId': album_info.get('qipuId', ''),
                            'duration': album_info.get('duration', 0)
                        })
            return results, data

        except Exception as e:
            print(f"获取视频列表失败: {e}")
            return [], None

    def get_video_info(self, data, target_qipu_id):
        """
        Extract video details from the given data.

        Parameters:
        - data: The full JSON response from get_video_list
        - target_qipu_id: The target qipuId to extract info from

        Returns:
        - dict or list: Dictionary containing video details or list of episodes
        """
        try:
            # 转为字符串，以统一比较格式
            target_qipu_id_str = str(target_qipu_id)
            
            if 'data' in data and 'templates' in data['data']:
                episodes = []
                main_video_info = None
                for template in data['data']['templates']:
                    if 'albumInfo' in template:
                        album_info = template['albumInfo']
                        album_qipu_id_str = str(album_info.get('qipuId', ''))
                        
                        # 如果找到匹配的视频ID
                        if album_qipu_id_str == target_qipu_id_str:
                            # 提取主视频信息
                            main_video_info = {
                                'title': album_info.get('title', ''),
                                'playUrl': album_info.get('playUrl', '').split(';')[0].split('=')[1] if album_info.get('playUrl') else '',
                                'duration': album_info.get('duration', 0)
                            }
                            
                            # 提取集数信息 (如果存在videos字段)
                            if 'videos' in album_info and isinstance(album_info['videos'], list):
                                for video in album_info['videos']:
                                    # 提取集数信息
                                    episode = {
                                        'title': video.get('title', '未知集数'),
                                        'playUrl': video.get('playUrl', '').split(';')[0].split('=')[1] if video.get('playUrl') else '',
                                        'duration': video.get('duration', 0),
                                        'qipuId': video.get('qipuId', ''),
                                        'number': video.get('number', '')
                                    }
                                    episodes.append(episode)
                                
                                # 如果找到了集数，则返回集数列表
                                if episodes:
                                    print(f"找到 {len(episodes)} 个集数")
                                    return episodes
                            
                            # 如果没有集数，则返回主视频信息
                            return main_video_info
                        
                        # 尝试在视频单集中寻找匹配
                        if 'videos' in album_info and isinstance(album_info['videos'], list):
                            for video in album_info['videos']:
                                video_qipu_id_str = str(video.get('qipuId', ''))
                                if video_qipu_id_str == target_qipu_id_str:
                                    # 返回单集信息
                                    return {
                                        'title': video.get('title', ''),
                                        'playUrl': video.get('playUrl', '').split(';')[0].split('=')[1] if video.get('playUrl') else '',
                                        'duration': video.get('duration', 0)
                                    }
            
            # 如果通过正常方式未找到，尝试在整个数据中搜索
            print(f"未在主结构中找到视频 {target_qipu_id}，尝试深度搜索...")
            return self._deep_search_video(data, target_qipu_id_str)
            
        except Exception as e:
            print(f"提取视频信息时出错: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def _deep_search_video(self, data, target_qipu_id_str):
        """深度搜索视频信息，处理复杂的嵌套结构"""
        try:
            # 在templates中搜索
            if 'data' in data and 'templates' in data['data']:
                for template in data['data']['templates']:
                    # 处理albumInfo情况
                    if 'albumInfo' in template:
                        album_info = template['albumInfo']
                        
                        # 检查qipuId
                        if str(album_info.get('qipuId', '')) == target_qipu_id_str:
                            return {
                                'title': album_info.get('title', ''),
                                'playUrl': album_info.get('playUrl', '').split(';')[0].split('=')[1] if album_info.get('playUrl') else '',
                                'duration': album_info.get('duration', 0)
                            }
                            
                        # 检查videos数组
                        if 'videos' in album_info:
                            for video in album_info['videos']:
                                if str(video.get('qipuId', '')) == target_qipu_id_str:
                                    return {
                                        'title': video.get('title', ''),
                                        'playUrl': video.get('playUrl', '').split(';')[0].split('=')[1] if video.get('playUrl') else '',
                                        'duration': video.get('duration', 0)
                                    }
            
            # 如果仍未找到，返回None
            print(f"在数据中未找到视频 {target_qipu_id_str}")
            return None
            
        except Exception as e:
            print(f"深度搜索视频时出错: {e}")
            return None

    def _generate_danmu_hash(self, tvid, seq_num):
        """Generate hash for danmu request"""
        BARRAGE_REQUEST_INTERVAL_TIME = "60"
        SECRET_KEY = "cbzuw1259a"
        
        content = f"{tvid}_{BARRAGE_REQUEST_INTERVAL_TIME}_{seq_num}{SECRET_KEY}"
        
        hash_value = hashlib.md5(content.encode()).hexdigest()[-8:]
        
        return hash_value

    def fetch_danmu(self, vid, duration):
        """
        Fetch danmu for a single video and save it to a CSV file.

        Parameters:
        - vid (str): The video ID
        - duration (int): Video duration in milliseconds

        Returns:
        - str: Path to the CSV file containing the fetched danmu
        """
        print(f"正在获取视频 {vid} 的弹幕")
        i_length = ceil(duration/60000)
        danmus = []
        
        vid_group1 = vid[-4:-2]
        vid_group2 = vid[-2:]
        
        for i in range(1, i_length + 1):
            hash_value = self._generate_danmu_hash(vid, i)
            url = f"https://cmts.iqiyi.com/bullet/{vid_group1}/{vid_group2}/{vid}_60_{i}_{hash_value}.br"
            print(f"获取片段 {i}: {url}")
            
            try:
                response = requests.get(url)
                if response.status_code != 200:
                    continue
                    
                dm_dc = brotli.decompress(response.content)
                danmu_msg = self.DanmuMessage()
                danmu_msg.ParseFromString(dm_dc)
                
                for entry in danmu_msg.entry:
                    for bullet in entry.bulletInfo:
                        try:
                            show_time = int(bullet.showTime)
                        except ValueError:
                            show_time = 0
                            
                        if bullet.content:
                            danmus.append({
                                'time_offset': show_time*1000,
                                'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'content': bullet.content
                            })
                            
            except Exception as e:
                print(f"处理片段 {i} 时出错: {e}")
                continue

        if danmus:
            df = pd.DataFrame(danmus)
            output_path = os.path.join(self.base_dir, f"video_{vid}_{len(danmus)}_danmu.csv")
            df.to_csv(output_path, encoding="utf-8", index=False)
            print(f"已保存 {len(danmus)} 条弹幕到 {output_path}")
            return output_path
            
        print(f"未获取到视频ID为 {vid} 的弹幕数据")
        return None

if __name__ == "__main__":
    scraper = AiqiyiVideoScraper(base_dir="danmu_data")
    query = "北上"
    video_list, data = scraper.get_video_list(query)
    print(f"找到 {len(video_list)} 个相关视频:")
    for idx, item in enumerate(video_list):
        print(f"{idx+1}. {item['title']} (视频ID: {item['qipuId']})")
    
    if video_list:
        # 尝试获取第一个视频的信息
        main_video_id = video_list[0]['qipuId']
        print(f"\n获取视频 {main_video_id} 的信息:")
        video_info = scraper.get_video_info(data, main_video_id)
        
        if isinstance(video_info, list):
            print(f"获取到 {len(video_info)} 个集数")
            for i, episode in enumerate(video_info[:5]):  # 只打印前5个，避免太多
                print(f"  集数 {i+1}: {episode['title']} (ID: {episode['qipuId']})")
            
            # 尝试获取第一集的弹幕
            if video_info and 'playUrl' in video_info[0] and video_info[0]['playUrl']:
                print(f"\n获取第一集弹幕:")
                tvid = video_info[0]['playUrl']
                duration = video_info[0]['duration']
                scraper.fetch_danmu(tvid, duration)
        else:
            print(f"视频信息: {video_info}")
            if video_info and 'playUrl' in video_info and video_info['playUrl']:
                # 尝试获取弹幕
                tvid = video_info['playUrl']
                duration = video_info['duration']
                scraper.fetch_danmu(tvid, duration)
                
    # 测试获取某个特定集数的信息
    specific_episode_id = 7319462550510300  # 第一集的ID
    print(f"\n获取特定集数 {specific_episode_id} 的信息:")
    episode_info = scraper.get_video_info(data, specific_episode_id)
    print(f"集数信息: {episode_info}") 