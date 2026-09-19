FROM python:3.12-alpine
RUN pip install --no-cache-dir paho-mqtt==2.1.0
COPY bridge.py /bridge.py
CMD ["python", "-u", "/bridge.py"]
