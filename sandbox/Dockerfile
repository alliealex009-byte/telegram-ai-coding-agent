FROM python:3.11-slim
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin sandbox
WORKDIR /workspace
USER 1000:1000
ENTRYPOINT ["python"]
