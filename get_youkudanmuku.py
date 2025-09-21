import aiohttp
import json
import urllib.parse
import re
import time
import hashlib
import base64
import os
import csv
import asyncio
from tqdm import tqdm
from retrying import retry
from datetime import datetime

class YoukuSearch:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://so.youku.com/",
        }
        self.search_pattern = re.compile(r'\"showId\":\"(.*?)\".*?\"tempTitle\":\"(.*?)\"')
        self.episodes_pattern_template = re.compile(r'"videoId":\s*"(.*?)".*?"title":\s*"{}(.*?)"')

    async def search(self, keyword):
        encoded_keyword = urllib.parse.quote(keyword)
        url = f"https://so.youku.com/search_video/q_{encoded_keyword}"
        print(url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    return await response.text()
        except aiohttp.ClientError as e:
            raise Exception(f"Search request failed: {str(e)}")

    def parse_search_results(self, html_content):
        matches = self.search_pattern.findall(html_content)
        return [{"title": match[1], "vid": f"https://v.youku.com/v_nextstage/id_{match[0]}.html?"} for match in matches]

    def get_episodes(self, html_content, title):
        """
        获取指定视频的集数列表
        :param html_content: HTML内容
        :param title: 视频标题
        :return: 集数列表
        """
        # 使用预编译的正则表达式模板创建特定标题的模式
        print(f"获取视频 '{title}' 的集数，HTML长度: {len(html_content) if html_content else 0}")
        
        # 处理特殊字符，确保转义
        escaped_title = re.escape(title)
        pattern = self.episodes_pattern_template.pattern.format(escaped_title)
        episode_pattern = re.compile(pattern)
        print(f"构建集数正则表达式: {pattern}")
        
        # 找到包含相关信息的JSON块以减少搜索范围
        start_idx = html_content.find('"videoId"')
        if start_idx == -1:
            print("未找到videoId标记，无法获取集数")
            return []
        end_idx = html_content.find('</script>', start_idx)
        if end_idx == -1:
            end_idx = len(html_content)
        
        # 在限定范围内进行匹配
        search_text = html_content[start_idx:end_idx]
        print(f"在搜索文本中查找集数，文本长度: {len(search_text)}")
        matches = episode_pattern.findall(search_text)
        
        # 输出匹配结果
        if matches:
            print(f"找到 {len(matches)} 个匹配项")
        else:
            print(f"未找到匹配项，尝试使用其他方法")
            
            # 如果找不到集数，尝试更宽松的匹配
            loose_pattern = r'"videoId":\s*"(.*?)".*?"title":\s*"(.*?第\d+集.*?)"'
            loose_matches = re.findall(loose_pattern, search_text)
            if loose_matches:
                print(f"使用宽松模式找到 {len(loose_matches)} 个集数")
                # 使用列表推导式构建结果
                return [{"Title": match[1], "vid": f"https://v.youku.com/v_show/id_{match[0]}.html"} for match in loose_matches]
        
        # 使用列表推导式构建结果
        results = [{"Title": f"{title}第{match[1]}集", "vid": f"https://v.youku.com/v_show/id_{match[0]}.html"} for match in matches]
        print(f"返回 {len(results)} 个集数")
        return results

class GetDanmuYouku:
    def __init__(self):
        self.cookies = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }

    @retry(stop_max_attempt_number=5, wait_random_min=1000, wait_random_max=2000)
    async def request_data(self, method, url, status_code=None, **kwargs):
        for attempt in range(5):
            try:
                async with aiohttp.ClientSession(cookies=self.cookies) as session:
                    async with session.request(method, url, **kwargs) as response:
                        if status_code:
                            if response.status == status_code:
                                # 更新cookies
                                self.cookies.update({k: v.value for k, v in response.cookies.items()})
                                return response
                            return None
                        # 更新cookies
                        self.cookies.update({k: v.value for k, v in response.cookies.items()})
                        if method.lower() == "get":
                            return await response.text()
                        else:
                            return await response.json()
            except aiohttp.ClientError:
                if attempt < 4:  # 如果不是最后一次尝试
                    await asyncio.sleep((attempt + 1) * 0.5)  # 随机延迟
                    continue
                raise
        return None

    async def get_auth_tokens(self):
        """获取认证所需的token"""
        await self.request_data("GET", "https://log.mmstat.com/eg.js", headers=self.headers)
        res = await self.request_data("GET",
                              "https://acs.youku.com/h5/mtop.com.youku.aplatform.weakget/1.0/?jsv=2.5.1&appKey=24679788",
                              headers=self.headers)
        return '_m_h5_tk' in self.cookies and '_m_h5_tk_enc' in self.cookies

    async def get_video_duration(self, video_id):
        """获取视频时长"""
        url = "https://openapi.youku.com/v2/videos/show.json"
        params = {
            'client_id': '53e6cc67237fc59a',
            'video_id': video_id,
            'package': 'com.huawei.hwvplayer.youku',
            'ext': 'show',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as response:
                result = await response.json()
                return result.get('duration')

    async def get_danmus(self, video_id, max_mat):
        """获取指定视频的所有弹幕"""
        danmus = []
        for mat in tqdm(range(0, int(float(max_mat) / 60) + 1), desc="Fetching danmus"):
            msg = self._prepare_danmu_request(video_id, mat)
            response = await self._send_danmu_request(msg)
            if response:
                danmus.extend(self._parse_danmu_response(response))
            # 防止请求过快
            await asyncio.sleep(0.2)
        return danmus

    def _prepare_danmu_request(self, video_id, mat):
        """准备弹幕请求参数"""
        msg = {
            'ctime': int(time.time() * 1000),
            'ctype': 10004,
            'cver': 'v1.0',
            'guid': self.cookies.get('cna'),
            'mat': mat,
            'mcount': 1,
            'pid': 0,
            'sver': '3.1.0',
            'type': 1,
            'vid': video_id
        }
        msg['msg'] = base64.b64encode(json.dumps(msg).replace(' ', '').encode('utf-8')).decode('utf-8')
        msg['sign'] = self._get_msg_sign(msg['msg'])
        return msg

    async def _send_danmu_request(self, msg):
        """发送弹幕请求"""
        url = "https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/"
        t = int(time.time() * 1000)
        params = {
            'jsv': '2.5.6',
            'appKey': '24679788',
            't': t,
            'sign': self._get_request_sign(t, msg),
            'api': 'mopen.youku.danmu.list',
            'v': '1.0',
            'type': 'originaljson',
            'dataType': 'jsonp',
            'timeout': '20000',
            'jsonpIncPrefix': 'utility'
        }
        headers = {**self.headers, 'Content-Type': 'application/x-www-form-urlencoded', 'Referer': 'https://v.youku.com'}
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            async with session.post(url, data={"data": json.dumps(msg).replace(' ', '')},
                              headers=headers, params=params) as response:
                return await response.json()

    def _parse_danmu_response(self, response):
        """解析弹幕响应数据"""
        danmus = []
        result = json.loads(response.get('data', {}).get('result', '{}'))
        if result.get('code') == '-1':
            return danmus
        
        for danmu in result.get('data', {}).get('result', []):
            danmus.append({
                'show_time': danmu.get('playat'), 
                'color': json.loads(danmu.get('propertis', '{}')).get('color', 16777215),
                'content': danmu.get('content', '')
            })
        return danmus

    def _get_msg_sign(self, msg_base64):
        """生成消息签名"""
        secret_key = 'MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr'
        return hashlib.md5((msg_base64 + secret_key).encode()).hexdigest()

    def _get_request_sign(self, t, msg):
        """生成请求签名"""
        token = self.cookies.get('_m_h5_tk', '')[:32]
        text = f"{token}&{t}&24679788&{json.dumps(msg).replace(' ', '')}"
        return hashlib.md5(text.encode()).hexdigest()

async def write_danmu_to_file(danmus, filename):
    """将弹幕数据写入CSV文件"""
    if not danmus:
        print("No danmu data to write")
        return

    if not os.path.exists('danmu_data/youku/'):
        os.makedirs('danmu_data/youku/')
        print('--- New Folder danmu_data/youku/ Created ---')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = f'danmu_data/youku/{filename}_{timestamp}.csv'

    print(f"--- Writing to file {filepath} ---")
    with open(filepath, 'w', encoding='utf-8', newline='') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=['show_time', 'color', 'content'])
        writer.writeheader()
        writer.writerows(danmus)
    print("--- DONE ---")

async def extract_real_vid_from_url(url):
    """
    从URL或HTML页面中提取真实的vid参数
    :param url: 视频URL
    :return: 视频真实vid
    """
    # 检查URL类型
    if 'v_nextstage' in url or 'video?s=' in url:
        # 提取s参数
        if 'v_nextstage/id_' in url:
            s_param = url.split('v_nextstage/id_')[1].split('.html')[0]
        elif 'video?s=' in url:
            s_param = url.split('video?s=')[1].split('&')[0]
        else:
            return None
        
        # 构造新URL
        new_url = f"https://v.youku.com/video?s={s_param}"
        
        # 发送请求获取页面内容
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(new_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}) as response:
                    html_content = await response.text()
                    
                    # 使用正则表达式提取vid参数
                    vid_pattern = re.compile(r'vid=([^&"]+)')
                    match = vid_pattern.search(html_content)
                    if match:
                        return match.group(1)
        except Exception as e:
            print(f"Error extracting vid from URL: {e}")
            return None
    # 如果是v_show类型的URL
    elif 'v_show/id_' in url:
        try:
            vid = url.split('v_show/id_')[1].split('.html')[0]
            return vid
        except:
            return None
    
    return None

async def get_video_danmus(video_info):
    """获取视频的弹幕数据并保存"""
    vid_url = video_info['vid']
    title = video_info['title']
    
    # 检查vid是否是URL形式，如果是则提取真实的vid参数
    if vid_url.startswith('http'):
        video_id = await extract_real_vid_from_url(vid_url)
        if not video_id:
            # 如果无法提取，尝试旧方法
            video_id = vid_url.split('id_')[1].split('.html')[0]
    else:
        video_id = vid_url

    print(f"Processing {title} (video_id: {video_id})")
    danmu_getter = GetDanmuYouku()
    
    # 获取认证token
    if not await danmu_getter.get_auth_tokens():
        print("Failed to get authentication tokens")
        return []

    # 获取视频时长
    duration = await danmu_getter.get_video_duration(video_id)
    if not duration:
        print("Failed to get video duration")
        return []

    # 获取弹幕
    danmus = await danmu_getter.get_danmus(video_id, duration)
    if danmus:
        await write_danmu_to_file(danmus, title)

    return danmus

async def search_videos(keyword):
    """
    搜索视频
    :param keyword: 搜索关键词
    :return: 搜索结果列表 [{"title": "标题", "vid": "视频URL"}]
    """
    searcher = YoukuSearch()
    try:
        result = await searcher.search(keyword)
        videos = searcher.parse_search_results(result)
        return videos, result
    except Exception as e:
        print(f"Search failed: {e}")
        return [], None

async def get_video_episodes(search_result, title):
    """
    获取视频的所有集数
    :param search_result: 搜索结果HTML内容
    :param title: 视频标题
    :return: 集数列表 [{"Title": "标题", "vid": "视频URL"}]
    """
    searcher = YoukuSearch()
    try:
        print(f"尝试使用标题 '{title}' 获取集数列表")
        episodes = searcher.get_episodes(search_result, title)
        
        # 如果没有找到集数信息（可能是电影），创建一个包含电影本身的集数项
        if not episodes and search_result:
            print(f"未找到 '{title}' 的集数信息，尝试将其作为单部电影处理")
            
            # 尝试从搜索结果中直接提取电影信息
            movies = searcher.parse_search_results(search_result)
            for movie in movies:
                print(f"检查电影: {movie['title']}")
                if movie['title'] == title or title in movie['title'] or movie['title'] in title:
                    print(f"找到匹配的电影: {movie['title']}")
                    # 提取真实的vid
                    real_vid = await extract_real_vid_from_url(movie['vid'])
                    if real_vid:
                        print(f"提取真实vid: {real_vid}")
                        episodes.append({
                            "Title": f"{movie['title']}",
                            "vid": real_vid
                        })
                    else:
                        print(f"无法提取真实vid，使用原始URL: {movie['vid']}")
                        episodes.append({
                            "Title": f"{movie['title']}",
                            "vid": movie['vid']
                        })
                    break
            
            # 如果上面的尝试也没找到匹配的电影，创建一个基于标题的默认项
            if not episodes:
                print(f"未找到匹配的电影，尝试从HTML中提取vid")
                # 尝试使用正则表达式直接从HTML中提取videoId
                # 正则表达式寻找 vid=XXX 格式的视频ID
                vid_pattern = re.compile(r'vid=([^&"\s]+)')
                match = vid_pattern.search(search_result)
                if match:
                    vid = match.group(1)
                    print(f"从HTML中提取到vid: {vid}")
                    episodes.append({
                        "Title": title,
                        "vid": vid
                    })
                    
                # 如果上面的正则没找到，再尝试其他方式
                if not episodes:
                    print("尝试其他正则表达式提取视频ID")
                    # 格式1：类似 "videoId":"XNjM3MzIzMDg4MA=="
                    video_id_pattern1 = re.compile(r'\"videoId\":\"([^\"]+)\".*?\"title\":\"({0}.*?)\"'.format(re.escape(title)))
                    # 格式2：直接从showId提取并构建URL
                    video_id_pattern2 = re.compile(r'\"showId\":\"([^\"]+)\".*?\"tempTitle\":\"({0})\"'.format(re.escape(title)))
                    
                    match = video_id_pattern1.search(search_result)
                    if match:
                        vid = match.group(1)
                        print(f"从videoId模式中提取到vid: {vid}")
                        episodes.append({
                            "Title": title,
                            "vid": vid
                        })
                    else:
                        match = video_id_pattern2.search(search_result)
                        if match:
                            # 构建URL并提取真实vid
                            show_id = match.group(1)
                            temp_url = f"https://v.youku.com/video?s={show_id}"
                            print(f"从showId中构建URL: {temp_url}")
                            real_vid = await extract_real_vid_from_url(temp_url)
                            if real_vid:
                                print(f"从URL提取真实vid: {real_vid}")
                                episodes.append({
                                    "Title": title,
                                    "vid": real_vid
                                })
                            else:
                                print(f"无法提取真实vid，使用原始URL")
                                episodes.append({
                                    "Title": title,
                                    "vid": temp_url
                                })
        
        print(f"最终获取到 {len(episodes)} 个集数")
        return episodes
    except Exception as e:
        print(f"获取集数失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

async def download_danmu(vid_url, title):
    """
    下载指定视频的弹幕
    :param vid_url: 视频URL
    :param title: 视频标题
    :return: 弹幕列表
    """
    try:
        video_info = {"title": title, "vid": vid_url}
        return await get_video_danmus(video_info)
    except Exception as e:
        print(f"Download danmu failed: {e}")
        return []

async def main():
    # 示例用法
    # 1. 搜索视频
    videos, search_result = await search_videos("沙尘暴")
    print(videos)
    print(search_result)
    if not videos:
        print("No videos found")
        return
    
    # 2. 获取集数列表
    episodes = await get_video_episodes(search_result, "沙尘暴")
    print(episodes)
    if not episodes:
        print("No episodes found")
        return
    
    # # 3. 下载特定集数的弹幕
    # first_episode = episodes[0]
    # danmus = await download_danmu(first_episode["vid"], first_episode["Title"])
    # print(f"Downloaded {len(danmus)} danmus for {first_episode['Title']}")

if __name__ == "__main__":
    asyncio.run(main()) 