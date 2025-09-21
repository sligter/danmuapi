import os
import requests
import urllib.parse
import re
import pandas as pd
from bs4 import BeautifulSoup
import json
import uuid
class TencentVideoScraper:
    """
    A class for scraping video lists, video details, and fetching danmu (comments) from Tencent Video.
    """

    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def get_video_list(self, query):
        """
        Fetch a list of videos matching the query from Tencent Video.

        Parameters:
        - query (str): The search query.

        Returns:
        - list of dict: List containing video titles and IDs.
        """
        # API URL
        api_url = 'https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch'
        
        # 构造请求参数
        params = {
            'vplatform': '2'
        }
        
        # 构造请求头
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://v.qq.com',
            'referer': 'https://v.qq.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'trpc-trans-info': '{"trpc-env":""}'
        }
        
        # 构造请求体
        data = {
            "version": "24072901",
            "clientType": 1,
            "filterValue": "",
            "uuid": str(uuid.uuid4()),
            "retry": 0,
            "query": query,
            "pagenum": 0,
            "pagesize": 30,
            "queryFrom": 0,
            "searchDatakey": "",
            "transInfo": "",
            "isneedQc": True,
            "preQid": "",
            "adClientInfo": "",
            "extraInfo": {
                "isNewMarkLabel": "1",
                "multi_terminal_pc": "1"
            }
        }
        
        response = requests.post(api_url, 
                            params=params,
                            headers=headers, 
                            json=data)
        response.raise_for_status()
        
        # 获取响应文本并保存以便调试
        response_text = response.text
        # with open('response_debug.txt', 'w', encoding='utf-8') as f:
        #     f.write(response_text)
        
        # 解析JSON响应
        result = json.loads(response_text)
        
        # 提取视频信息
        video_info_list = []
        
        try:
            # 首先从 normalList 中获取数据
            items = result.get('data', {}).get('normalList', {}).get('itemList', [])
            for item in items:
                try:
                    doc = item.get('doc', {})
                    video_info = item.get('videoInfo', {})
                    
                    if doc and video_info:
                        doc_id = doc.get('id', '')
                        title = video_info.get('title', '')
                        
                        if doc_id and title:
                            video_info_list.append({
                                'id': doc_id,
                                'title': title
                            })
                except Exception as e:
                    print(f"处理normalList项目时出错: {e}")
                    continue
            
            # 然后检查并合并 areaBoxList 中的数据
            area_box_list = result.get('data', {}).get('areaBoxList', [])
            if area_box_list:
                for box in area_box_list:
                    items = box.get('itemList', [])
                    for item in items:
                        try:
                            doc = item.get('doc', {})
                            video_info = item.get('videoInfo', {})
                            
                            if doc and video_info:
                                doc_id = doc.get('id', '')
                                title = video_info.get('title', '')
                                
                                if doc_id and title:
                                    # 检查是否已存在相同的id
                                    if not any(x['id'] == doc_id for x in video_info_list):
                                        video_info_list.append({
                                            'id': doc_id,
                                            'title': title
                                        })
                        except Exception as e:
                            print(f"处理areaBoxList项目时出错: {e}")
                            continue
                        
        except Exception as e:
            print(f"处理响应数据时出错: {e}")
        
        return video_info_list

    def get_video_info(self, video_id):
        """
        Fetch video details such as title and VID using the video ID.

        Parameters:
        - video_id (str): The unique ID of the video.

        Returns:
        - list of dict: List containing playTitle and vid.
        """
        url = f'https://v.qq.com/x/cover/{video_id}.html'
        print(url)
        try:
            response = requests.get(url)
            response.raise_for_status()
            response.encoding = 'utf-8'
            html_content = response.text
            with open('response_debug.txt', 'w', encoding='utf-8') as f:
                f.write(html_content)
        except requests.RequestException as e:
            print(f"Error fetching video info: {e}")
            return []

        pattern = re.compile(r'\"vid\":\"(.*?)\".*?\"playTitle\":\"(.*?)\"')
        matches = pattern.findall(html_content)
        result = [{"playTitle": match[1], "vid": match[0]} for match in matches[::-1]]
        
        # 提取cid
        cid_pattern = re.compile(r'\"cid\":\s*\"(.*?)\"')
        cid_match = cid_pattern.search(html_content)
        cid = cid_match.group(1) if cid_match else video_id
        
        # 检查是否有分页信息
        has_next_page = False
        next_page_context = None
        
        # 尝试提取分页信息
        page_info_pattern = re.compile(r'\"pageInfos\":\s*\[\s*{\s*\"hasNextPage\":\s*(true|false),\s*\"hasPrevPage\":\s*(true|false),\s*\"nextPageContext\":\s*\"(.*?)\"')
        page_info_matches = page_info_pattern.search(html_content)
        
        if page_info_matches:
            has_next_page = page_info_matches.group(1) == 'true'
            next_page_context = page_info_matches.group(3)
        
        # 提取标签页信息
        tabs_pattern = re.compile(r'\"tabs\":\s*(\[.*?\]),\"tabIndex\"')
        tabs_match = tabs_pattern.search(html_content)
        
        # 处理标签页信息
        if tabs_match:
            try:
                tabs_json = tabs_match.group(1)
                tabs = json.loads(tabs_json)
                
                # 对每个标签页获取集数信息
                for tab in tabs:
                    # 跳过已选中的标签页，因为其内容已经在主页面处理过了
                    if tab.get('isSelected', False):
                        continue
                    
                    page_context = tab.get('pageContext', '')
                    if page_context:
                        print(f"Processing tab: {tab.get('text', '')}")
                        # 使用标签页上下文获取该标签页的集数信息
                        tab_episodes = self._get_tab_episodes(cid, page_context)
                        if tab_episodes:
                            result.extend(tab_episodes)
            except Exception as e:
                print(f"Error processing tabs: {e}")
        
        # 如果有下一页，获取下一页的集数
        if has_next_page and next_page_context:
            # 使用额外请求获取下一页数据
            try:
                next_page_data = self._get_next_page_episodes(cid, next_page_context)
                if next_page_data:
                    result.extend(next_page_data)
            except Exception as e:
                print(f"Error fetching next page data: {e}")
        
        return result

    def _get_tab_episodes(self, cid, page_context):
        """
        获取特定标签页的集数信息
        
        Parameters:
        - cid (str): 内容ID
        - page_context (str): 标签页请求所需的上下文参数
        
        Returns:
        - list of dict: 包含playTitle和vid的集数列表
        """
        url = 'https://pbaccess.video.qq.com/trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData'
        params = {
            'video_appid': '3000010',
            'vplatform': '2',
            'vversion_name': '8.2.96'
        }
        
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://v.qq.com',
            'referer': 'https://v.qq.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        
        # 从page_context中提取参数
        params_dict = {}
        param_pairs = page_context.split('&')
        for pair in param_pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                params_dict[key] = value
        
        payload = {
            "page_params": {
                "req_from": "web_vsite",
                "page_id": "vsite_episode_list",
                "page_type": "detail_operation",
                "id_type": "1",
                "cid": cid,
                # 添加从page_context提取的关键参数
                "page_num": params_dict.get("page_num", "0"),
                "page_size": params_dict.get("page_size", "30"),
                "episode_begin": params_dict.get("episode_begin", ""),
                "episode_end": params_dict.get("episode_end", ""),
                "tab_type": params_dict.get("tab_type", "1")
            },
            "has_cache": 1
        }
        
        try:
            response = requests.post(url, params=params, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # 解析返回的结果，提取集数信息
            result = []
            module_list_datas = data.get('data', {}).get('module_list_datas', [])
            
            for module in module_list_datas:
                module_datas = module.get('module_datas', [])
                
                for mod_data in module_datas:
                    item_data_lists = mod_data.get('item_data_lists', {})
                    item_datas = item_data_lists.get('item_datas', [])
                    
                    for item in item_datas:
                        # 只处理类型为'1'的项目，表示视频内容
                        if item.get('item_type') == '1' or item.get('item_type') == 1:
                            item_params = item.get('item_params', {})
                            vid = item_params.get('vid', '')
                            play_title = item_params.get('play_title', '')
                            
                            if vid and play_title:
                                result.append({
                                    "playTitle": play_title,
                                    "vid": vid
                                })
            
            print(f"在标签页中找到 {len(result)} 个视频")
            return result
        except Exception as e:
            print(f"Error in _get_tab_episodes: {e}")
            return []

    def _get_next_page_episodes(self, cid, page_context):
        """
        获取下一页的集数信息
        
        Parameters:
        - cid (str): 内容ID
        - page_context (str): 下一页请求所需的上下文参数
        
        Returns:
        - list of dict: 包含playTitle和vid的集数列表
        """
        url = 'https://pbaccess.video.qq.com/trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData'
        params = {
            'video_appid': '3000010',
            'vplatform': '2',
            'vversion_name': '8.2.96'
        }
        
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://v.qq.com',
            'referer': 'https://v.qq.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        
        payload = {
            "page_params": {
                "req_from": "web_vsite",
                "page_id": "vsite_episode_list",
                "page_type": "detail_operation",
                "id_type": "1",
                "page_size": "",
                "cid": cid,
                "vid": "",
                "lid": "",
                "page_num": "",
                "page_context": page_context
            },
            "has_cache": 1
        }
        
        try:
            response = requests.post(url, params=params, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            # print(data)  # 调试时可保留
            
            # 解析返回的结果，提取集数信息
            result = []
            module_list_datas = data.get('data', {}).get('module_list_datas', [])
            
            for module in module_list_datas:
                module_datas = module.get('module_datas', [])
                
                # 处理新的数据结构
                for mod_data in module_datas:
                    item_data_lists = mod_data.get('item_data_lists', {})
                    item_datas = item_data_lists.get('item_datas', [])
                    
                    for item in item_datas:
                        # 只处理类型为'1'的项目，表示视频内容
                        if item.get('item_type') == '1' or item.get('item_type') == 1:
                            item_params = item.get('item_params', {})
                            vid = item_params.get('vid', '')
                            play_title = item_params.get('play_title', '')
                            
                            if vid and play_title:
                                result.append({
                                    "playTitle": play_title,
                                    "vid": vid
                                })
                                # 打印找到的视频，便于调试
                                # print(f"Found video: {play_title} - {vid}")
            
            print(f"总共找到 {len(result)} 个视频")
            return result
        except Exception as e:
            print(f"Error in _get_next_page_episodes: {e}")
            return []

    def fetch_danmu(self, video_code, num=10000, step=30000):
        """
        Fetch danmu (barrage) for a single video code and save it to a CSV file.

        Parameters:
        - video_code (str): The unique code of the video.
        - num (int): Maximum number of requests (default: 10000).
        - step (int): Time range step in milliseconds for each request (default: 30000ms).

        Returns:
        - str: Path to the CSV file containing the fetched danmu.
        """
        episodes_danmu_DataFrame = pd.DataFrame()
        total_danmu_count = 0

        for i in range(num):
            url = f'https://dm.video.qq.com/barrage/segment/{video_code}/t/v1/{i * step}/{(i + 1) * step}'
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()

                if "barrage_list" in data and len(data["barrage_list"]) > 0:
                    temp_danmu_DataFrame = pd.json_normalize(data["barrage_list"], errors='ignore')
                    episodes_danmu_DataFrame = pd.concat([episodes_danmu_DataFrame, temp_danmu_DataFrame])

                    batch_count = temp_danmu_DataFrame.shape[0]
                    total_danmu_count += batch_count

                    print(f"Request #{i+1}: Retrieved {batch_count} danmu, Total={total_danmu_count}")
                else:
                    print(f"No more danmu found at Request #{i+1}. Stopping.")
                    break

            except Exception as e:
                print(f"Error fetching data from {url}: {e}")
                break

        if not episodes_danmu_DataFrame.empty:
            output_path = os.path.join(self.base_dir, f"video_{video_code}_{total_danmu_count}_danmu.csv")
            episodes_danmu_DataFrame = episodes_danmu_DataFrame.loc[:, ['time_offset', 'create_time', 'content']]
            episodes_danmu_DataFrame.to_csv(output_path, mode='w', encoding="utf-8", errors='ignore', index=False)
            print(f"Danmu saved to {output_path}")
            return output_path

        print(f"No danmu data fetched for video_code={video_code}.")
        return None

if __name__ == "__main__":
    scraper = TencentVideoScraper(base_dir="danmu_data")
    query = "庆余年第二季"
    video_list = scraper.get_video_list(query)
    print(video_list)
    item_list = scraper.get_video_info(video_list[0]['id'])
    print(item_list)
    # video_info = scraper.get_video_info("mzc00200y41tzil")
    # print(video_info)
    # scraper.fetch_danmu('v41002r8czq')
    # print(item_list[0]['playTitle'])
