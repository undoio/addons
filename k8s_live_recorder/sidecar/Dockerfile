FROM golang:1.24-alpine AS builder

ENV GOOS=linux
ENV GOARCH=amd64
ENV CGO_ENABLED=0

WORKDIR /build
COPY . .

RUN go mod download
RUN go build -o undo-recorder-agent .

FROM debian:bookworm-slim

ENV LIVE_RECORD_PATH=/undo/live-record
ENV UNDOLR_PATH=/undo/undolr
ENV RECORDINGS_DIR=/recordings

# Required for uploading to S3
RUN apt-get update && apt-get install -y ca-certificates  

RUN mkdir -p /undo /recordings /tmp

COPY --from=builder /build/undo-recorder-agent /undo/undo-recorder-agent
COPY live-record /undo/live-record
COPY undolr /undo/undolr

RUN chmod +x /undo/undo-recorder-agent /undo/live-record

ENTRYPOINT ["/undo/undo-recorder-agent"]
