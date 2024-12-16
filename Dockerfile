FROM python:3.13-alpine

USER root

# Runtime dependency
RUN apk add --no-cache ffmpeg

RUN pip install markitdown

USER 10000:10000

ENTRYPOINT [ "markitdown" ]
