# ToolGate container image — build: docker build -t toolgate .
FROM python:3.12-slim

# Run as an unprivileged user
RUN useradd --create-home --uid 1001 toolgate

WORKDIR /app
COPY --chown=toolgate:toolgate . /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Persistent state (sqlite db, optional master.key) lives here
ENV TOOLGATE_HOME=/data
RUN mkdir -p /data && chown toolgate:toolgate /data
VOLUME ["/data"]

USER toolgate
EXPOSE 8848

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8848/healthz').status==200 else 1)"

ENTRYPOINT ["toolgate", "serve", "--host", "0.0.0.0"]
CMD ["--port", "8848"]
