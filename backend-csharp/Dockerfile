FROM mcr.microsoft.com/dotnet/runtime-deps:9.0

WORKDIR /app

# 安装必要的依赖（curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY bin/publish-linux/ /app/

RUN chmod +x /app/backend-csharp

EXPOSE 8000
ENV ASPNETCORE_URLS=http://0.0.0.0:8000

HEALTHCHECK --interval=10s --timeout=5s --retries=20 \
  CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/backend-csharp"]
