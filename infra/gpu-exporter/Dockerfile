FROM python:3.12-slim
RUN pip install --no-cache-dir "prometheus-client>=0.20,<1"
WORKDIR /app
COPY fake_dcgm_exporter.py .
CMD ["python", "-u", "fake_dcgm_exporter.py"]
