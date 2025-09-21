# LibreTV 弹幕服务

一个基于 Flask 的多平台弹幕聚合与分发服务，支持腾讯视频、爱奇艺、B站、优酷、芒果TV 的弹幕搜索、集数获取与下载，并提供 DPlayer 兼容的弹幕读写 API。

核心后端入口：[app.py](app.py)  
数据抓取与适配器：[danmaku_loader.py](danmaku_loader.py)  
构建与运行容器：[Dockerfile](Dockerfile)  
项目依赖定义：[pyproject.toml](pyproject.toml)  
前端脚本示例：[js/index-page.js](js/index-page.js)

运行入口位置：[app.run()](app.py:679)  
关键 API 注册位置：
- DPlayer 弹幕 API：[app.route('/api/dplayer/v3/')](app.py:33)
- 搜索弹幕接口：[app.route('/api/danmaku/search')](app.py:228)
- 获取集数接口：[app.route('/api/danmaku/episodes')](app.py:278)
- 下载弹幕接口：[app.route('/api/danmaku/download')](app.py:516)
- 清空缓存接口：[app.route('/api/danmaku/clearCache')](app.py:192)

容器健康检查与启动：  
- 健康检查指令：[HEALTHCHECK](Dockerfile:34)  
- 暴露端口：[EXPOSE](Dockerfile:31)  
- 启动命令：[CMD](Dockerfile:37)

---

## 功能特性

- 多平台弹幕抓取与聚合：腾讯(“企鹅”) / 爱奇艺(“奇异”) / B站(“阿B”) / 优酷(“阿酷”) / 芒果(“阿芒”)
- DPlayer 兼容弹幕 API：读取/发送弹幕、持久化 JSON
- 弹幕 CSV 清洗与兼容解析（自动处理 NUL 字符、时间格式）
- 简单静态资源服务（根路径返回静态页面，便于与前端整合）
- Docker 一键构建运行，包含健康检查

---

## 目录结构

- [app.py](app.py) Flask 应用与全部 API 路由
- [danmaku_loader.py](danmaku_loader.py) 平台抓取适配封装
- 平台抓取器
  - get_tencent_danmu.py（腾讯）
  - get_aiqiyi_danmu.py（爱奇艺）
  - get_bilibili_danmu.py（B站）
  - get_youkudanmuku.py（优酷）
  - get_mgtv_danmu.py（芒果）
- 数据与静态
  - danmu_data/ 各平台 CSV 与 DPlayer JSON 缓存（启动/运行时会自动创建）
  - js/ 前端脚本示例（如 [js/index-page.js](js/index-page.js)）
- 构建与依赖
  - [pyproject.toml](pyproject.toml)
  - [Dockerfile](Dockerfile)
  - uv.lock

---

## 环境要求

- Python >= 3.11（见 [pyproject.toml](pyproject.toml)）
- 依赖管理：uv 或 pip
- 运行端口：5005（容器/本地均为 5005）

---

## 安装与运行

### 方式一：使用 uv（推荐）

1) 安装 uv
```
pip install uv
```

2) 安装依赖
```
uv sync --frozen
```

3) 运行服务
```
uv run python app.py
```
默认监听 0.0.0.0:5005，生产建议配合反向代理。

### 方式二：使用 pip

1) 创建并激活虚拟环境（可选）
```
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2) 安装依赖
```
pip install -r <(uv pip compile pyproject.toml)
```
或根据 [pyproject.toml](pyproject.toml) 手动安装所需依赖。

3) 运行服务
```
python app.py
```

---

## Docker 部署

1) 构建镜像
```
docker build -t libretv:latest .
```

2) 启动容器（映射端口与数据目录）
```
docker run -d --name libretv \
  -p 5005:5005 \
  -v ${PWD}/danmu_data:/app/danmu_data \
  libretv:latest
```

容器内健康检查：[HEALTHCHECK](Dockerfile:34) 会每 30s 访问 http://localhost:5005/。

---

## API 文档

所有接口基于 JSON，出现错误时会返回形如：
```
{"code": 4xx/5xx, "message": "错误描述"}
```
成功时一般返回：
```
{"code": 200, ...}
```

### 源标识（source 参数）

- “企鹅” = 腾讯视频
- “奇异” = 爱奇艺
- “阿B” = 哔哩哔哩
- “阿酷” = 优酷
- “阿芒” = 芒果TV

### 1) 搜索视频

[app.route('/api/danmaku/search')](app.py:228)

GET /api/danmaku/search?keyword=三体&source=阿B

返回示例：
```
{
  "code": 200,
  "videos": [
    {"id": "BV1xxxx", "title": "三体 第一季"},
    ...
  ]
}
```

### 2) 获取集数

[app.route('/api/danmaku/episodes')](app.py:278)

GET /api/danmaku/episodes?videoId=xxxx&source=奇异&keyword=三体

- 注意：部分平台需要 keyword 辅助匹配更准确的专辑/剧集。
- 返回示例：
```
{
  "code": 200,
  "episodes": [
    {"id": "playUrlOrVid", "title": "第1集"},
    ...
  ]
}
```

### 3) 下载弹幕（标准化 JSON）

[app.route('/api/danmaku/download')](app.py:516)

GET /api/danmaku/download?danmakuId=xxxx&source=企鹅&keyword=三体

返回示例（按时间升序）：
```
{
  "code": 200,
  "danmakus": [
    {"time": 12345, "text": "这是一个弹幕(毫秒)"},
    ...
  ],
  "count": 1000
}
```

兼容处理：
- 自动去除 CSV 中的 NUL 字符
- 支持毫秒与 “HH:MM:SS” 格式时间解析
- 针对腾讯/爱奇艺/优酷/芒果/B站不同列名做映射

### 4) DPlayer 弹幕 API（读写）

[app.route('/api/dplayer/v3/')](app.py:33)

- 读取（GET）
  - 参数：id（视频唯一标识），max（返回最大条数，默认 1000）
  - 响应 data 为 DPlayer 弹幕数组：[time, type, color, author, text]
- 写入（POST）
  - JSON：{id, author?, text, color?, type?, time?}
  - 服务端会将弹幕存入内存并同步持久化到 danmu_data/dplayer/{id}.json

示例（读取）：
```
GET /api/dplayer/v3/?id=BV1xxxx&max=300
{
  "code": 0,
  "data": [
    [12.3, 0, 16777215, "guest", "Hello DPlayer!"],
    ...
  ]
}
```

示例（写入）：
```
POST /api/dplayer/v3/
{"id": "BV1xxxx", "author": "me", "text": "来了", "time": 10}
-> {"code": 0, "data": [10, 0, 16777215, "me", "来了"]}
```

自动导入机制：
- 首次 GET 时若内存/文件无数据，服务将尝试从 danmu_data/{platform}/*.csv 中匹配 safe_id（id 清洗后的片段）并转换为 DPlayer 格式缓存。

### 5) 清空弹幕缓存

[app.route('/api/danmaku/clearCache')](app.py:192)

POST /api/danmaku/clearCache

- 清空内存缓存与 danmu_data/{bilibili,youku,tencent,iqiyi,mgtv,dplayer} 下的 .csv/.json 文件
- 返回删除文件数

---

## DPlayer 前端集成示例

最小化示例（以页面中已有播放器容器 #player 为例）：
```
<script src="https://unpkg.com/dplayer/dist/DPlayer.min.js"></script>
<div id="player"></div>
<script>
  const videoId = 'BV1xxxx'; // 与后端 DPlayer API 的 id 一致
  const dp = new DPlayer({
    container: document.getElementById('player'),
    video: {
      url: 'https://example.com/video.mp4'
    },
    danmaku: {
      id: videoId,
      api: 'http://localhost:5005/api/dplayer/v3/'
    }
  });
</script>
```

若要实现从 URL 自动读取搜索参数并初始化，可参考前端脚本：[js/index-page.js](js/index-page.js)

---

## 数据持久化与存储布局

服务启动/运行时会确保以下目录存在（容器内路径 /app）：
- danmu_data/dplayer 存放 DPlayer JSON（按 id 命名）
- danmu_data/tencent、danmu_data/iqiyi、danmu_data/bilibili、danmu_data/youku、danmu_data/mgtv
  - 各平台下载的原始 CSV 文件

挂载示例（Docker）：
```
-v ${PWD}/danmu_data:/app/danmu_data
```

---

## 常见问题

- 访问跨域
  - 已开启 CORS（见 Flask-CORS 依赖），可跨域调用后端 API。
- 爱奇艺/优酷 集数或时长匹配不准确
  - 请同时传入 keyword，后端会利用检索结果辅助匹配；服务内部包含多重回退逻辑以尽可能找到时长或剧集列表。
- CSV 编码/字符异常
  - 读取时会先去除 NUL，再解析为 UTF-8；如仍异常，请提供样例文件进行定位。
- 端口占用
  - 默认端口 5005，可在外层反代映射；当前 [app.py](app.py) 内部固定 5005。

---

## 开发提示

- 新增平台时，参考现有抓取器接口规范，在 [danmaku_loader.py](danmaku_loader.py) 中统一封装搜索/集数/下载三件套。
- 若要扩展 API，请在 [app.py](app.py) 中新增路由，并考虑：
  - 输入校验、错误处理
  - 跨域与缓存策略
  - 数据格式与兼容性（保持现有字段命名）

---

## 许可证

未声明（如需开放源代码协议，请在此添加 LICENSE 说明）。
