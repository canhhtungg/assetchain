FROM golang:1.25-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN go build -o assetcc .

FROM alpine:3.20

WORKDIR /app

COPY --from=builder /app/assetcc .

RUN chmod +x /app/assetcc

ENTRYPOINT ["/app/assetcc"]
