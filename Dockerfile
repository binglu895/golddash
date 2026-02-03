# 使用官方 Python 3.10 轻量版镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 防止 Python 生成pyc文件
ENV PYTHONDONTWRITEBYTECODE=1
# 保持控制台输出不被缓冲，方便查看日志
ENV PYTHONUNBUFFERED=1

# 更新 pip 并安装依赖
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目所有文件到工作目录
COPY . .

# 暴露 8080 端口 (PaaS 平台通用标准)
EXPOSE 8080

# 启动命令
# --server.port=8080 : 改用 8080 端口，配合 Zeabur 默认探测
# --browser.gatherUsageStats=false : 生产环境关闭统计，减少日志噪音
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
