FROM python:3.13-slim

WORKDIR /app

COPY requirements.docker.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt


COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .


COPY examples/device_watcher.py .
COPY lynxConf.json .

CMD ["python", "examples/device_watcher.py"]
