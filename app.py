from flask import Flask, request, jsonify, send_from_directory, Response
import os
import asyncio
import pandas as pd
from pathlib import Path
import json
import traceback
import time
from flask_cors import CORS  # 导入CORS扩展

# 导入弹幕相关模块
from danmaku_loader import TencentVideoScraper, AiqiyiVideoScraper, BilibiliVideoScraper, MgtvVideoScraper
from get_youkudanmuku import search_videos, get_video_episodes, download_danmu

app = Flask(__name__, static_folder=".")
CORS(app)  # 启用CORS支持，允许所有域的请求

# 初始化弹幕爬取器
tencent_scraper = TencentVideoScraper(base_dir="danmu_data")
aiqiyi_scraper = AiqiyiVideoScraper(base_dir="danmu_data")
bilibili_scraper = BilibiliVideoScraper(base_dir="danmu_data")
mgtv_scraper = MgtvVideoScraper(base_dir="danmu_data")

# 确保弹幕数据目录存在
os.makedirs("danmu_data", exist_ok=True)
os.makedirs("danmu_data/youku", exist_ok=True)
os.makedirs("danmu_data/dplayer", exist_ok=True)  # DPlayer弹幕数据目录

# DPlayer弹幕数据存储
DPLAYER_DANMAKU_DATA = {}  # 内存中存储弹幕数据，格式: {id: [弹幕列表]}

# DPlayer弹幕API路由
@app.route('/api/dplayer/v3/', methods=['GET', 'POST'])
def dplayer_danmaku():
    if request.method == 'GET':
        # 获取弹幕
        id = request.args.get('id')
        max_count = int(request.args.get('max', 1000))
        
        if not id:
            return jsonify({"code": 0, "data": []})
        
        # 尝试从内存中获取
        danmaku_list = DPLAYER_DANMAKU_DATA.get(id, [])
        
        # 如果内存中没有，尝试从文件加载
        if not danmaku_list:
            try:
                file_path = os.path.join("danmu_data", "dplayer", f"{id}.json")
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        danmaku_data = json.load(f)
                        DPLAYER_DANMAKU_DATA[id] = danmaku_data
                        danmaku_list = danmaku_data
            except Exception as e:
                print(f"加载弹幕文件失败: {e}")
        
        # 导入其他平台已下载的弹幕 - 增加视频ID检查，防止混淆不同视频弹幕
        if not danmaku_list:
            try:
                # 仅当当前弹幕ID与视频ID匹配时才导入
                danmaku_list = import_danmaku_from_other_sources(id)
                if danmaku_list:
                    DPLAYER_DANMAKU_DATA[id] = danmaku_list
                    # 保存到文件
                    save_dplayer_danmaku(id, danmaku_list)
            except Exception as e:
                print(f"导入其他平台弹幕失败: {e}")
        
        # 返回弹幕，最多max_count条
        return jsonify({
            "code": 0,
            "data": danmaku_list[:max_count]
        })
    
    elif request.method == 'POST':
        # 发送弹幕
        data = request.json or {}
        id = data.get('id')
        author = data.get('author', 'guest')
        text = data.get('text', '')
        color = data.get('color', 16777215)  # 默认白色
        type = data.get('type', 0)           # 默认滚动弹幕
        time = data.get('time', 0)           # 时间点，单位秒
        
        if not id or not text:
            return jsonify({"code": -1, "msg": "参数不完整"})
        
        # 创建新弹幕
        danmaku = [time, type, color, author, text]
        
        # 添加到内存
        if id not in DPLAYER_DANMAKU_DATA:
            DPLAYER_DANMAKU_DATA[id] = []
        DPLAYER_DANMAKU_DATA[id].append(danmaku)
        
        # 保存到文件
        save_dplayer_danmaku(id, DPLAYER_DANMAKU_DATA[id])
        
        return jsonify({"code": 0, "data": danmaku})

def save_dplayer_danmaku(id, danmaku_list):
    try:
        file_path = os.path.join("danmu_data", "dplayer", f"{id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(danmaku_list, f, ensure_ascii=False)
    except Exception as e:
        print(f"保存弹幕文件失败: {e}")

def import_danmaku_from_other_sources(id):
    """从其他平台导入已下载的弹幕到DPlayer格式"""
    danmaku_list = []
    
    # 保存弹幕ID的部分用于匹配文件
    # 需要防止ID过长或包含无效字符
    safe_id = "".join(c for c in id if c.isalnum() or c in ['-', '_']).lower()[:50]
    if not safe_id:
        safe_id = id  # 如果清理后为空，则保持原ID
    
    print(f"尝试导入弹幕, ID: {id}, 安全ID: {safe_id}")
    
    # 搜索所有弹幕目录
    for platform in ['bilibili', 'youku', 'tencent', 'iqiyi', 'mgtv']:
        dir_path = os.path.join("danmu_data", platform)
        if not os.path.exists(dir_path):
            continue
        
        for file_name in os.listdir(dir_path):
            if not file_name.endswith('.csv'):
                continue
            
            # 只匹配对应ID的弹幕文件，防止不同视频弹幕混合
            if safe_id and safe_id not in file_name.lower():
                continue
            
            try:
                file_path = os.path.join(dir_path, file_name)
                print(f"找到匹配的弹幕文件: {file_path}")
                
                # 读取CSV文件
                df = pd.read_csv(file_path)
                
                # 根据不同平台处理数据格式
                if platform == 'tencent':
                    for _, row in df.iterrows():
                        time_ms = int(row.get('time_offset', 0))
                        text = row.get('content', '')
                        if text:
                            # DPlayer格式: [time, type, color, author, text]
                            danmaku_list.append([time_ms/1000, 0, 16777215, 'guest', text])
                else:
                    # 尝试获取时间和内容列
                    time_col = next((col for col in df.columns if 'time' in col.lower()), df.columns[0])
                    text_col = next((col for col in df.columns if 'content' in col.lower() or 'text' in col.lower()), df.columns[-1])
                    
                    for _, row in df.iterrows():
                        try:
                            time_val = row[time_col]
                            text = row[text_col]
                            
                            # 处理不同格式的时间
                            if isinstance(time_val, str) and ':' in time_val:
                                # 时:分:秒 格式转换为秒
                                parts = time_val.split(':')
                                if len(parts) == 3:
                                    time_val = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                                elif len(parts) == 2:
                                    time_val = int(parts[0]) * 60 + float(parts[1])
                            else:
                                # 假设是毫秒，转换为秒
                                time_val = float(time_val) / 1000
                            
                            if text:
                                danmaku_list.append([time_val, 0, 16777215, 'guest', str(text)])
                        except Exception as e:
                            print(f"处理弹幕数据出错: {e}")
                            continue
            except Exception as e:
                print(f"读取弹幕文件出错: {e}")
    
    # 按时间排序
    danmaku_list.sort(key=lambda x: x[0])
    print(f"导入了 {len(danmaku_list)} 条弹幕")
    
    return danmaku_list

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

# 添加清空弹幕缓存的API
@app.route('/api/danmaku/clearCache', methods=['POST'])
def clear_danmaku_cache():
    try:
        # 清空内存中的弹幕数据
        global DPLAYER_DANMAKU_DATA
        DPLAYER_DANMAKU_DATA = {}
        
        # 清空各平台本地弹幕文件
        platforms = ['bilibili', 'youku', 'tencent', 'iqiyi', 'mgtv', 'dplayer']
        deleted_files = 0
        
        for platform in platforms:
            dir_path = os.path.join("danmu_data", platform)
            if not os.path.exists(dir_path):
                continue
                
            for filename in os.listdir(dir_path):
                if filename.endswith('.csv') or filename.endswith('.json'):
                    file_path = os.path.join(dir_path, filename)
                    try:
                        os.remove(file_path)
                        deleted_files += 1
                    except Exception as e:
                        print(f"删除文件 {file_path} 失败: {e}")
        
        return jsonify({"code": 200, "message": f"已清空弹幕缓存，删除了 {deleted_files} 个文件"})
    except Exception as e:
        print(f"清空弹幕缓存失败: {e}")
        print(traceback.format_exc())
        return jsonify({"code": 500, "message": f"清空弹幕缓存失败: {str(e)}"})

@app.route('/<path:path>')
def static_file(path):
    return send_from_directory('.', path)

# 弹幕搜索API
@app.route('/api/danmaku/search')
def search_danmaku():
    keyword = request.args.get('keyword', '')
    source = request.args.get('source', '企鹅')

    if not keyword:
        return jsonify({"code": 400, "message": "请提供搜索关键词"})

    try:
        if source == "企鹅":
            video_list = tencent_scraper.get_video_list(keyword)
            return jsonify({
                "code": 200,
                "videos": [{"id": v["id"], "title": v["title"]} for v in video_list]
            })
        elif source == "奇异":
            video_list, _ = aiqiyi_scraper.get_video_list(keyword)
            return jsonify({
                "code": 200,
                "videos": [{"id": v["qipuId"], "title": v["title"]} for v in video_list]
            })
        elif source == "阿B":
            video_list, _ = bilibili_scraper.get_video_list(keyword)
            return jsonify({
                "code": 200,
                "videos": [{"id": v["id"], "title": v["title"]} for v in video_list]
            })
        elif source == "阿酷":
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            videos, _ = loop.run_until_complete(search_videos(keyword))
            loop.close()
            return jsonify({
                "code": 200,
                "videos": [{"id": v["vid"], "title": v["title"]} for v in videos]
            })
        elif source == "阿芒":
            videos, _ = mgtv_scraper.get_video_list(keyword)
            return jsonify({
                "code": 200,
                "videos": [{"id": v["vid"], "title": v["title"]} for v in videos]
            })
        else:
            return jsonify({"code": 400, "message": f"不支持的弹幕源: {source}"})
    except Exception as e:
        print(f"搜索弹幕失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"code": 500, "message": f"搜索弹幕失败: {str(e)}"})

# 获取集数API
@app.route('/api/danmaku/episodes')
def get_danmaku_episodes():
    video_id = request.args.get('videoId', '')
    source = request.args.get('source', '企鹅')
    keyword = request.args.get('keyword', '')  # 确保获取keyword参数

    if not video_id:
        return jsonify({"code": 400, "message": "请提供视频ID"})

    try:
        if source == "企鹅":
            episode_list = tencent_scraper.get_video_info(video_id)
            return jsonify({
                "code": 200,
                "episodes": [{"id": episode["vid"], "title": episode["playTitle"]} for episode in episode_list]
            })
        elif source == "奇异":
            # 对于爱奇艺，需要调用另一个API方法
            try:
                # 先使用传入的keyword或video_id进行搜索
                search_term = keyword if keyword else video_id
                print(f"爱奇艺弹幕搜索关键词: {search_term}")
                
                video_list, data = aiqiyi_scraper.get_video_list(search_term)
                if not video_list:
                    return jsonify({"code": 404, "message": "未找到视频信息"})
                
                # 尝试匹配视频ID
                matched_video = None
                for video in video_list:
                    if str(video["qipuId"]) == str(video_id):
                        matched_video = video
                        break
                
                if not matched_video:
                    print(f"未找到匹配的爱奇艺视频ID: {video_id}")
                    # 如果找不到匹配的视频，使用第一个
                    matched_video = video_list[0]
                    print(f"使用第一个视频: {matched_video['title']} (ID: {matched_video['qipuId']})")
                
                # 获取视频集数信息
                video_info = aiqiyi_scraper.get_video_info(data, int(matched_video["qipuId"]))
                
                # 检查返回结果类型
                if isinstance(video_info, list):
                    # 如果返回的是集数列表，提取每集信息
                    episodes = []
                    for episode in video_info:
                        if 'playUrl' in episode and episode['playUrl']:
                            episodes.append({
                                "id": episode["playUrl"],
                                "title": episode["title"],
                                "qipuId": episode.get("qipuId", "")
                            })
                    
                    if not episodes:
                        return jsonify({"code": 404, "message": "未找到集数信息"})
                    
                    print(f"找到 {len(episodes)} 个集数")
                    return jsonify({"code": 200, "episodes": episodes})
                
                elif video_info:  # 单个视频情况
                    return jsonify({
                        "code": 200,
                        "episodes": [{
                            "id": video_info["playUrl"], 
                            "title": video_info["title"]
                        }]
                    })
                else:
                    # 尝试获取更多集数信息
                    episodes = []
                    if data and 'data' in data:
                        for template in data.get('data', {}).get('templates', []):
                            if 'albumInfo' in template and str(template['albumInfo'].get('qipuId', '')) == str(matched_video["qipuId"]):
                                # 如果是剧集，检查videos数组
                                videos = template['albumInfo'].get('videos', [])
                                if videos:
                                    for video in videos:
                                        play_url = ""
                                        if video.get('playUrl'):
                                            parts = video.get('playUrl').split(';')
                                            if parts and '=' in parts[0]:
                                                play_url = parts[0].split('=')[1]
                                        
                                        episodes.append({
                                            "id": play_url,
                                            "title": video.get('title', '未命名'),
                                            "qipuId": video.get('qipuId', '')
                                        })
                                else:
                                    # 如果没有videos数组，直接添加当前项
                                    play_url = ""
                                    if template['albumInfo'].get('playUrl'):
                                        parts = template['albumInfo'].get('playUrl').split(';')
                                        if parts and '=' in parts[0]:
                                            play_url = parts[0].split('=')[1]
                                    
                                    episodes.append({
                                        "id": play_url,
                                        "title": template['albumInfo'].get('title', '未命名'),
                                        "qipuId": template['albumInfo'].get('qipuId', '')
                                    })
                                break
                    
                    if not episodes:
                        return jsonify({"code": 404, "message": "未找到集数信息"})
                    
                    return jsonify({"code": 200, "episodes": episodes})
            except Exception as e:
                print(f"获取爱奇艺集数失败: {str(e)}")
                print(traceback.format_exc())
                return jsonify({"code": 500, "message": f"获取集数失败: {str(e)}"})
        elif source == "阿B":
            # 对于B站，需要先获取视频数据
            try:
                # 使用关键词或视频ID进行搜索
                search_keyword = keyword if keyword else video_id
                print(f"使用关键词搜索B站视频: {search_keyword}")
                
                # 先用关键词搜索获取视频列表和数据
                videos, data = bilibili_scraper.get_video_list(search_keyword)
                
                if not videos:
                    print(f"未找到与关键词匹配的视频: {search_keyword}")
                    return jsonify({"code": 404, "message": "未找到视频信息"})
                
                # 然后使用视频ID获取集数信息
                print(f"使用视频ID获取集数列表: {video_id}")
                episode_list = bilibili_scraper.get_video_info(data, video_id)
                
                if not episode_list:
                    print(f"找到视频但未找到集数信息，ID: {video_id}")
                    return jsonify({"code": 200, "episodes": []})
                
                # 返回集数列表
                return jsonify({
                    "code": 200,
                    "episodes": [{"id": episode["playUrl"], "title": episode["title"]} for episode in episode_list]
                })
            except Exception as e:
                print(f"获取B站集数失败: {str(e)}")
                print(traceback.format_exc())
                return jsonify({"code": 500, "message": f"获取集数失败: {str(e)}"})
        elif source == "阿酷":
            try:
                # 使用关键词进行搜索
                search_term = keyword if keyword else video_id
                print(f"使用关键词搜索优酷视频: {search_term}")
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 先进行搜索获取search_result
                videos, search_result = loop.run_until_complete(search_videos(search_term))
                
                if not videos:
                    print(f"未找到与关键词匹配的优酷视频: {search_term}")
                    return jsonify({"code": 404, "message": "未找到视频信息"})
                
                # 查找匹配视频ID的视频标题
                video_title = None
                for video in videos:
                    # 尝试完全匹配视频ID
                    if video["vid"] == video_id:
                        video_title = video["title"]
                        print(f"找到精确匹配的优酷视频: {video_title}")
                        break
                
                # 如果找不到精确匹配，默认使用第一个视频的标题
                if not video_title:
                    video_title = videos[0]["title"]
                    print(f"未找到精确匹配，使用第一个视频: {video_title}")
                
                # 使用标题来获取集数
                print(f"使用标题 '{video_title}' 获取集数")
                episodes = loop.run_until_complete(get_video_episodes(search_result, video_title))
                loop.close()
                
                if not episodes:
                    print(f"未找到 '{video_title}' 的集数信息")
                    return jsonify({"code": 404, "message": "未找到集数信息"})
                
                print(f"找到 {len(episodes)} 个集数")
                return jsonify({
                    "code": 200,
                    "episodes": [{"id": episode["vid"], "title": episode["Title"]} for episode in episodes]
                })
            except Exception as e:
                print(f"获取优酷集数失败: {str(e)}")
                print(traceback.format_exc())
                return jsonify({"code": 500, "message": f"获取集数失败: {str(e)}"})
        elif source == "阿芒":
            # 对于芒果TV，需要先获取视频信息
            try:
                # 使用关键词或视频ID进行搜索
                search_term = keyword if keyword else video_id
                print(f"使用关键词搜索芒果TV视频: {search_term}")
                
                videos, search_result = mgtv_scraper.get_video_list(search_term)
                
                if not videos:
                    print(f"未找到芒果TV视频: {search_term}")
                    return jsonify({"code": 404, "message": "未找到视频信息"})
                
                # 查找匹配的视频ID
                matched_video = None
                for v in videos:
                    if v["vid"] == video_id:
                        matched_video = v
                        break
                
                if not matched_video:
                    # 如果找不到匹配的视频，使用第一个
                    matched_video = videos[0]
                
                episodes = mgtv_scraper.get_video_info(search_result, matched_video["vid"])
                
                if not episodes:
                    print(f"找到视频但未找到集数信息，ID: {matched_video['vid']}")
                    return jsonify({"code": 200, "episodes": []})
                
                return jsonify({
                    "code": 200,
                    "episodes": [{"id": episode["url"], "title": episode["title"]} for episode in episodes]
                })
            except Exception as e:
                print(f"获取芒果TV集数失败: {str(e)}")
                print(traceback.format_exc())
                return jsonify({"code": 500, "message": f"获取集数失败: {str(e)}"})
        else:
            return jsonify({"code": 400, "message": f"不支持的弹幕源: {source}"})
    except Exception as e:
        print(f"获取集数失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"code": 500, "message": f"获取集数失败: {str(e)}"})

# 下载弹幕API
@app.route('/api/danmaku/download')
def download_danmaku():
    danmaku_id = request.args.get('danmakuId', '')
    source = request.args.get('source', '企鹅')
    keyword = request.args.get('keyword', '')  # 获取关键词参数用于标题处理

    if not danmaku_id:
        return jsonify({"code": 400, "message": "请提供弹幕ID"})

    try:
        filepath = None
        # 使用关键词或ID作为标题基础
        title_base = keyword if keyword else danmaku_id
        
        if source == "企鹅":
            filepath = tencent_scraper.fetch_danmu(danmaku_id)
        elif source == "奇异":
            # 爱奇艺弹幕获取，需要视频id和时长
            duration = 7200000  # 默认2小时
            
            # 先尝试通过API搜索获取相关信息
            if keyword:
                try:
                    print(f"搜索爱奇艺视频: {keyword}")
                    video_list, data = aiqiyi_scraper.get_video_list(keyword)
                    
                    if video_list:
                        # 尝试找到匹配的视频
                        matched_video = None
                        for video in video_list:
                            # 比较qipuId
                            if str(video.get('qipuId', '')) == str(danmaku_id):
                                matched_video = video
                                break
                                
                            # 在playUrl中查找
                            play_url = video.get('playUrl', '')
                            if play_url and danmaku_id in play_url:
                                matched_video = video
                                break
                        
                        # 如果找到匹配视频
                        if matched_video:
                            # 获取视频详细信息
                            video_info = aiqiyi_scraper.get_video_info(data, matched_video['qipuId'])
                            
                            # 可能返回列表(剧集)或单个对象(单视频)
                            if isinstance(video_info, list):
                                # 在视频列表中查找匹配ID的视频
                                for episode in video_info:
                                    if str(episode.get('qipuId', '')) == str(danmaku_id) or episode.get('playUrl', '') == danmaku_id:
                                        duration = episode.get('duration', 7200000)
                                        print(f"从视频列表中找到匹配视频: {episode.get('title')}, 时长: {duration}")
                                        break
                            elif video_info:
                                duration = video_info.get('duration', 7200000)
                                print(f"找到视频信息: {video_info.get('title')}, 时长: {duration}")
                except Exception as e:
                    print(f"搜索爱奇艺视频信息失败: {e}")
                    
            print(f"获取爱奇艺弹幕: ID={danmaku_id}, 时长={duration}")
            filepath = aiqiyi_scraper.fetch_danmu(danmaku_id, duration)
        elif source == "阿B":
            filepath = bilibili_scraper.fetch_danmu(danmaku_id, title_base)
        elif source == "阿酷":
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            danmus = loop.run_until_complete(download_danmu(danmaku_id, title_base))
            loop.close()
            
            if danmus:
                # 查找最新的弹幕文件
                base_dir = "danmu_data/youku"
                files = [f for f in os.listdir(base_dir) if f.endswith('.csv')]
                if files:
                    latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(base_dir, x)))
                    filepath = os.path.join(base_dir, latest_file)
        elif source == "阿芒":
            filepath = mgtv_scraper.fetch_danmu(danmaku_id, title_base)
        else:
            return jsonify({"code": 400, "message": f"不支持的弹幕源: {source}"})

        if not filepath or not os.path.exists(filepath):
            return jsonify({"code": 404, "message": "未找到弹幕数据"})

        # 读取弹幕数据
        danmakus = []
        try:
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
                df = pd.read_csv(f)
                
                # 根据不同的弹幕源，处理不同格式的CSV
                if source == "企鹅":
                    # 企鹅视频的弹幕格式：time_offset, create_time, content
                    for _, row in df.iterrows():
                        danmakus.append({
                            "time": int(row['time_offset']),
                            "text": row['content']
                        })
                elif source in ["奇异", "阿B", "阿酷", "阿芒"]:
                    # 其他源的弹幕格式可能不同，需要适配
                    for _, row in df.iterrows():
                        # 检查列名
                        time_col = next((col for col in df.columns if 'time' in col.lower()), df.columns[0])
                        text_col = next((col for col in df.columns if 'content' in col.lower() or 'text' in col.lower()), df.columns[-1])
                        
                        try:
                            # 尝试提取时间
                            time_val = row[time_col]
                            if isinstance(time_val, str) and ':' in time_val:
                                # 如果是时分秒格式，转换为毫秒
                                parts = time_val.split(':')
                                if len(parts) == 3:
                                    time_val = (int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])) * 1000
                                elif len(parts) == 2:
                                    time_val = (int(parts[0]) * 60 + float(parts[1])) * 1000
                            
                            danmakus.append({
                                "time": int(float(time_val)),
                                "text": str(row[text_col])
                            })
                        except (ValueError, TypeError) as e:
                            print(f"处理弹幕行时出错: {e}, 原行: {row}")
                            continue
            
            # 删除临时文件
            try:
                os.remove(temp_filepath)
            except:
                pass
            
            # 按时间排序
            danmakus.sort(key=lambda x: x["time"])
            
            # 输出日志
            print(f"成功加载 {len(danmakus)} 条弹幕")
            
            return jsonify({
                "code": 200,
                "danmakus": danmakus,
                "count": len(danmakus)
            })
        except Exception as e:
            print(f"读取弹幕数据失败: {str(e)}")
            print(traceback.format_exc())
            return jsonify({"code": 500, "message": f"读取弹幕数据失败: {str(e)}"})
    except Exception as e:
        print(f"下载弹幕失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"code": 500, "message": f"下载弹幕失败: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=False) 