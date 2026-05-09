# GTM Agency OS — runtime image.
# Non-root user, minimal base, no build toolchain in the final image.

FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only top-level deps first to keep the layer cache warm.
COPY pyproject.toml README.md ./
COPY gtmos ./gtmos
RUN pip install --upgrade pip && pip install .

# ---- runtime image ---------------------------------------------------------

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GTMOS_LOG_LEVEL=INFO

# Non-root by default. Use a deterministic uid/gid so volume mounts behave.
RUN groupadd --system --gid 10001 gtmos \
 && useradd --system --uid 10001 --gid gtmos --create-home --shell /sbin/nologin gtmos

WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --chown=gtmos:gtmos . /app

USER gtmos

# Default port for `gtmos slack-app`. Override with -p at run.
EXPOSE 3000

ENTRYPOINT ["gtmos"]
CMD ["--help"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import gtmos; print(gtmos.__version__)"]
