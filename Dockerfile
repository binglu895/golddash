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

# 暴露 Streamlit 默认端口
EXPOSE 8501

# 启动命令
# --server.address=0.0.0.0 : 允许外部需访问
# --server.port=8501 : 指定端口
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
