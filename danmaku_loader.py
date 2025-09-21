import csv
import os
import asyncio
from pathlib import Path
from get_tencent_danmu import TencentVideoScraper
from get_aiqiyi_danmu import AiqiyiVideoScraper
from get_youkudanmuku import search_videos, get_video_episodes, download_danmu  # 导入优酷相关函数
from get_mgtv_danmu import MgtvVideoScraper  # 导入阿芒相关类
from get_bilibili_danmu import BilibiliVideoScraper

class DanmakuLoader:
    def __init__(self):
        os.makedirs("danmu_data", exist_ok=True)
        
        # 初始化不同平台的爬虫
        self.tencent_scraper = TencentVideoScraper(base_dir="danmu_data")
        self.aiqiyi_scraper = AiqiyiVideoScraper(base_dir="danmu_data")
        self.bilibili_scraper = BilibiliVideoScraper(base_dir="danmu_data")  # 添加B站爬虫
        self.mgtv_scraper = MgtvVideoScraper(base_dir="danmu_data")
        
        self.current_source = "企鹅"  # 默认源
        self.current_video_data = None
        self.current_youku_search_result = None
        self.current_mgtv_search_result = None  # 存储阿芒搜索结果

    def setSource(self, source):
        """设置当前视频源"""
        self.current_source = source
        print(f"Current source set to: {source}")

    def searchVideo(self, query):
        """搜索视频"""
        print(f"Searching for video on {self.current_source}: {query}")
        try:
            if self.current_source == "企鹅":
                video_list = self.tencent_scraper.get_video_list(query)
                return video_list, None
            elif self.current_source == "奇异":
                video_list, data = self.aiqiyi_scraper.get_video_list(query)
                self.current_video_data = data
                return video_list, None
            elif self.current_source == "阿B":  # 添加B站支持
                video_list, data = self.bilibili_scraper.get_video_list(query)
                self.current_video_data = data
                return video_list, None
            elif self.current_source == "阿酷":
                # 为异步函数创建事件循环并运行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                videos, search_result = loop.run_until_complete(search_videos(query))
                loop.close()
                self.current_youku_search_result = search_result
                video_list = [{
                    "title": v["title"],
                    "id": v["vid"]
                } for v in videos]
                return video_list, None
            elif self.current_source == "阿芒":  # 添加阿芒支持
                videos, search_result = self.mgtv_scraper.get_video_list(query)
                self.current_mgtv_search_result = search_result
                video_list = [{"title": v["title"], "id": v["vid"]} for v in videos]
                return video_list, None
        except Exception as e:
            print(f"搜索失败: {str(e)}")
            raise e

    def getEpisodeList(self, video_id):
        """获取视频集数列表"""
        try:
            if self.current_source == "企鹅":
                episode_list = self.tencent_scraper.get_video_info(video_id)
                return episode_list
            elif self.current_source == "奇异":
                # 爱奇艺API更新，支持获取集数列表
                result = self.aiqiyi_scraper.get_video_info(self.current_video_data, video_id)
                
                # 结果可能是单集信息或集数列表
                if isinstance(result, list):
                    # 如果返回的是集数列表，直接使用
                    formatted_episodes = []
                    for episode in result:
                        # 检查必要信息是否存在
                        if 'title' in episode and 'playUrl' in episode:
                            formatted_episodes.append({
                                'title': episode['title'],
                                'playUrl': episode['playUrl'],
                                'duration': episode.get('duration', 0),
                                'qipuId': episode.get('qipuId', '')
                            })
                    return formatted_episodes
                elif result:
                    # 如果是单个视频(电影)，创建一个集数条目
                    formatted_episodes = [{
                        'title': result['title'],
                        'playUrl': result['playUrl'],
                        'duration': result.get('duration', 0)
                    }]
                    return formatted_episodes
                else:
                    # 尝试深度搜索集数
                    formatted_episodes = []
                    if self.current_video_data and 'data' in self.current_video_data:
                        for template in self.current_video_data.get('data', {}).get('templates', []):
                            if 'albumInfo' in template and str(template['albumInfo'].get('qipuId', '')) == str(video_id):
                                # 获取videos数组
                                videos = template['albumInfo'].get('videos', [])
                                for video in videos:
                                    # 提取每集信息
                                    play_url = ""
                                    if video.get('playUrl'):
                                        parts = video.get('playUrl').split(';')
                                        if parts and '=' in parts[0]:
                                            play_url = parts[0].split('=')[1]
                                    
                                    formatted_episodes.append({
                                        'title': video.get('title', '未命名'),
                                        'playUrl': play_url,
                                        'duration': video.get('duration', 0),
                                        'qipuId': video.get('qipuId', '')
                                    })
                    
                    if formatted_episodes:
                        return formatted_episodes
                    else:
                        # 如果还是没找到集数，至少返回当前视频
                        print(f"没有找到集数列表，使用当前视频作为单集")
                        return [{
                            'title': '第1集',
                            'playUrl': video_id,  # 使用video_id作为播放URL
                            'duration': 0
                        }]
            elif self.current_source == "阿B":
                episode_list = self.bilibili_scraper.get_video_info(self.current_video_data, video_id)
                formatted_episodes = [{
                    'title': episode['title'],
                    'playUrl': episode['playUrl'],
                    'duration': episode['duration']
                } for episode in episode_list]
                return formatted_episodes
            elif self.current_source == "阿酷":
                # 为异步函数创建事件循环并运行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                episodes = loop.run_until_complete(get_video_episodes(self.current_youku_search_result, video_id))
                loop.close()
                formatted_episodes = [{
                    'title': episode['Title'],
                    'playUrl': episode['vid'],
                    'duration': 0
                } for episode in episodes]
                return formatted_episodes
            elif self.current_source == "阿芒":  # 添加阿芒支持
                episodes = self.mgtv_scraper.get_video_info(self.current_mgtv_search_result, video_id)
                formatted_episodes = [{
                    'title': episode['title'],
                    'playUrl': episode['url'],
                    'duration': 0
                } for episode in episodes]
                return formatted_episodes
        except Exception as e:
            print(f"获取集数失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e

    def downloadDanmaku(self, vid, title=None):
        """下载弹幕"""
        try:
            filepath = None
            
            if self.current_source == "企鹅":
                filepath = self.tencent_scraper.fetch_danmu(vid)
            elif self.current_source == "奇异":
                # 爱奇艺弹幕获取，需要视频id和时长
                duration = None
                
                # 尝试查找对应的视频信息，从视频列表中找到匹配的视频
                if self.current_video_data:
                    for template in self.current_video_data.get('data', {}).get('templates', []):
                        if 'albumInfo' in template:
                            album_info = template['albumInfo']
                            # 检查videos列表中的每个视频
                            for video in album_info.get('videos', []):
                                # 检查playUrl中是否包含当前vid
                                play_url = video.get('playUrl', '')
                                if play_url and vid in play_url:
                                    duration = video.get('duration', 0)
                                    print(f"找到匹配的视频，duration = {duration}")
                                    break
                                    
                                # 或者直接比较qipuId
                                video_id = video.get('qipuId', '')
                                if str(video_id) == str(vid):
                                    duration = video.get('duration', 0)
                                    print(f"通过qipuId找到视频，duration = {duration}")
                                    break
                                
                                # 从playUrl提取tvid参数
                                if play_url:
                                    try:
                                        for part in play_url.split(';'):
                                            if part.startswith('tvid='):
                                                tvid = part.split('=')[1]
                                                if str(tvid) == str(vid):
                                                    duration = video.get('duration', 0)
                                                    print(f"从tvid参数找到视频，duration = {duration}")
                                                    break
                                    except Exception as e:
                                        print(f"解析playUrl失败: {e}")
                
                if not duration:
                    # 默认时长，确保能获取完整弹幕
                    duration = 7200000  # 2小时
                    print(f"未找到视频时长，使用默认值: {duration}")
                
                print(f"开始获取爱奇艺弹幕，VID: {vid}, 时长: {duration}")
                filepath = self.aiqiyi_scraper.fetch_danmu(vid, duration)
            elif self.current_source == "阿B":
                # 获取当前视频标题
                title = title or "bilibili视频"
                filepath = self.bilibili_scraper.fetch_danmu(vid, title)
            elif self.current_source == "阿酷":
                # 为异步函数创建事件循环并运行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                danmus = loop.run_until_complete(download_danmu(vid, title or "阿酷"))
                loop.close()
                
                if danmus:
                    # 查找最新的弹幕文件
                    base_dir = "danmu_data/youku"
                    files = [f for f in os.listdir(base_dir) if f.endswith('.csv')]
                    if files:
                        latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(base_dir, x)))
                        filepath = os.path.join(base_dir, latest_file)
            elif self.current_source == "阿芒":
                # 获取当前视频标题
                title = title or "阿芒视频"
                filepath = self.mgtv_scraper.fetch_danmu(vid, title)
            else:
                raise Exception(f"暂不支持的视频源: {self.current_source}")

            return filepath
        except Exception as e:
            print(f"下载弹幕失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e

    def loadDanmaku(self, filepath):
        """加载弹幕文件"""
        try:
            danmaku_data = []
            # 先读取并清理文件内容
            with open(filepath, 'rb') as f:
                content = f.read()
                # 移除 NUL 字符
                content = content.replace(b'\x00', b'')
            
            # 将清理后的内容写回临时文件
            temp_filepath = filepath + '.temp'
            with open(temp_filepath, 'wb') as f:
                f.write(content)
            
            # 读取清理后的文件
            with open(temp_filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, escapechar='\\', quoting=csv.QUOTE_MINIMAL)
                next(reader)  # 跳过标题行
                for row in reader:
                    if len(row) >= 3:
                        time_field = row[0]
                        try:
                            time_value = int(time_field)
                            if time_value >= 0:
                                # 清理文本中的特殊字符
                                text = row[2].replace('\n', ' ').replace('\r', '').strip()
                                if text:  # 只添加非空文本
                                    danmaku_data.append({
                                        'time': time_value,
                                        'text': text
                                    })
                        except ValueError:
                            continue
                        except Exception as e:
                            print(f"Error processing row: {str(e)}")
                            continue
            
            # 删除临时文件
            try:
                os.remove(temp_filepath)
            except:
                pass
            
            return danmaku_data
            
        except Exception as e:
            print(f"Error loading danmaku: {str(e)}")
            raise e