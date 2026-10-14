# DEMO agent (made-up data). Build from this folder, passing the SDK's
# python/ folder as the named build context "sdk":
#   docker build -t review-actions-demo:0.1.0 --build-context sdk=<path-to-sdk-clone>/python .
FROM python:3.13-slim AS build-sdk
RUN pip install --no-cache-dir build
COPY --from=sdk . /sdk-source
WORKDIR /sdk-source
RUN python -m build --wheel --outdir /wheels

FROM python:3.13-slim
RUN groupadd --system agent && useradd --system --gid agent --create-home agent
WORKDIR /app
COPY --from=build-sdk /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY main.py ./
USER agent
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=8s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health', timeout=2).status == 200 else 1)"
ENTRYPOINT ["python", "-u", "main.py"]
