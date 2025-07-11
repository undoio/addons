FROM golang:1.24-alpine AS builder

RUN apk add --no-cache gcc musl-dev sqlite-dev

ENV GOOS=linux
ENV GOARCH=amd64
ENV CGO_ENABLED=1

WORKDIR /build
COPY main.go .
COPY go.mod .
COPY go.sum .

RUN go mod download
RUN go build -o broken-go-app main.go

FROM alpine

RUN apk add --no-cache sqlite

WORKDIR /app
COPY --from=builder /build/broken-go-app /app/

EXPOSE 8080
CMD ["/app/broken-go-app"]