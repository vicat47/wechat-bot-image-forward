FROM python:slim-buster

COPY requirements.txt /app/
WORKDIR /app/
VOLUME /app/data

RUN sed -i 's/http:\/\/deb.debian.org/https:\/\/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list \
    && apt-get update \
    && apt-get -y install gcc \
    && pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

EXPOSE 34567
COPY . /app/
ENTRYPOINT ["python", "app.py"]