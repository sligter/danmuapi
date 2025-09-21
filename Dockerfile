# 使用官方Python 3.11镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*


# 复制项目文件
COPY pyproject.toml uv.lock ./

# 安装uv包管理器
RUN pip install uv

# 使用uv安装Python依赖
RUN uv sync --frozen

# 复制应用代码
COPY . .

# 创建弹幕数据目录
RUN mkdir -p danmu_data/youku danmu_data/dplayer danmu_data/bilibili danmu_data/tencent danmu_data/iqiyi danmu_data/mgtv

# 暴露端口
EXPOSE 5005

# 设置健康检查（指定命令并使用暴露的端口）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:5005/ || exit 1

# 启动应用
CMD ["uv", "run", "python", "app.py"]
