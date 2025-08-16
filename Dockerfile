FROM python:3.13.5-bookworm

# 设置工作目录
WORKDIR /app

ENV PYTHONPATH="${PYTHONPATH}:/app"

COPY . .
RUN cp -r /app/deploy/supervisor /etc/supervisor

RUN pip3 install -r requirements.txt

# 设置环境变量
ENV C_FORCE_ROOT=True

# 设置可执行权限
RUN chmod +x run.sh

# 暴露端口
EXPOSE 8080

# 设置入口命令
ENTRYPOINT ["./run.sh"]