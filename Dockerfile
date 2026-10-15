# syntax=docker/dockerfile:1
# OWL Server image. The shared OWL core is installed from git by default; to build against a
# different revision use --build-arg OWL_SPEC="owl @ https://github.com/.../archive/<ref>.tar.gz".

FROM python:3.13-slim AS builder
ARG OWL_SPEC="owl @ https://github.com/MichaelWeissDEV/OWL/archive/refs/heads/master.tar.gz"
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir "${OWL_SPEC}" && pip install --no-cache-dir .

FROM python:3.13-slim
LABEL org.opencontainers.image.title="OWL Server" \
      org.opencontainers.image.description="Self-hostable skill registry for OWL" \
      org.opencontainers.image.source="https://github.com/MichaelWeissDEV/owl-server"
# unprivileged user, no shell login, no home directory content
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin owl
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    FORWARDED_ALLOW_IPS="127.0.0.1" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER owl
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=4).status == 200 else 1)"]
# uvicorn shuts down gracefully on SIGTERM; migrations run on start (OWL_SERVER_AUTO_MIGRATE).
ENTRYPOINT ["owl-server"]
# FORWARDED_ALLOW_IPS: proxies whose X-Forwarded-* headers are trusted (set it to your proxy network)
CMD ["serve", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers"]
