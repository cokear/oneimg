# 阶段1: 使用官方Go镜像作为构建环境
FROM golang:1.24-alpine AS builder

# 安装CGO编译所需的工具、库以及Node.js（用于Vue构建）
RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    libwebp-dev \
    nodejs \
    npm

# 安装pnpm（用于前端包管理）
RUN npm install -g pnpm

# 设置工作目录
WORKDIR /app

# 复制go.mod和go.sum文件，下载Go依赖
COPY go.mod go.sum ./
RUN go mod download

# 复制项目所有文件到工作目录（包括frontend目录）
COPY . .

# ---------------------- 前端构建流程 ----------------------
# 进入frontend目录
WORKDIR /app/frontend

# 安装前端依赖
RUN pnpm install

# 构建Vue项目（产物默认输出到dist目录）
RUN pnpm run build

# ---------------------- 后端构建流程 ----------------------
# 返回项目根目录
WORKDIR /app

# 启用CGO以支持webp库的编译
RUN GOOS=linux go build -a -installsuffix cgo -o main ./main.go

# 阶段2: 使用轻量级Alpine镜像作为运行环境
FROM alpine:3.18

# 安装运行时依赖
RUN apk --no-cache add \
    ca-certificates \
    tzdata \
    libwebp

# 设置工作目录
WORKDIR /app

# 从构建阶段复制编译好的后端应用
COPY --from=builder /app/main .

# 从构建阶段复制前端构建产物（dist目录）到后端服务的静态文件目录
# 这里假设你的Go服务会从 ./web 目录提供静态文件，可根据实际情况修改路径
COPY --from=builder /app/frontend/dist ./web

# 暴露应用端口（根据你的应用需要修改）
EXPOSE 8080

# 运行应用
CMD ["./main"]