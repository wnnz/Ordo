# Ordo C# (.NET 10) 单体后端

Ordo AI 工作流平台的高性能 C# 原生后端工程。

## 架构亮点

1. **单体聚合架构（Monolithic Convergence）**：
   - 移除原有的 Celery Worker、Celery Beat 与 Redis 容器。
   - API 接入、Channel 任务排队、BackgroundService 队列消费与定时工作流调度统一合并在一个轻量 .NET 进程内。
2. **100% 兼容现有 PostgreSQL 数据**：
   - 采用 EF Core + Npgsql 严格匹配原有 19 张数据表与 JSONB 格式。
   - 密码哈希采用与原 Python 100% 兼容的 Argon2id。
   - 敏感凭据加解密采用 Fernet 算法，完美解密原数据库中存储的 API Key 与环境变量。
3. **极简极速 Docker 部署**：
   - 编译为 self-contained 单文件二进制，冷启动仅需数十毫秒。
   - 运行镜像无需安装 .NET SDK/Runtime，内存开销下降 70% 以上。

## 目录组织

- `Data/`：EF Core 数据库上下文与 19 个独立数据实体（`User`, `Workspace`, `Workflow`, `WorkflowRun` 等）。
- `Common/`：
  - `Security/`：`FernetCryptography`、`PasswordHasherService`（Argon2id）、`JwtTokenService`。
  - `Configuration/`：系统环境变量绑定。
  - `Auth/`：`CurrentUserContext` 当前登录用户上下文。
- `Engine/`：DAG 工作流图校验、拓扑执行、变量解析与各节点执行器（Start, End, Variable, Template, Http, HostInfo, RdpDisconnect, Human, Llm, Script 等）。
- `Background/`：基于 `Channel<T>` 的异步 Worker 消费与定时调度器。
- `Controllers/`：管理端与公开应用端标准 Web API 控制器。
- `Services/`：进程内事件发布流（SSE 流式推流）。

## 启动与运行

```powershell
# 编译与单元测试
dotnet test ../backend-csharp.tests

# 发布 Linux 容器单文件二进制
dotnet publish -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -o bin/publish-linux

# 启动 Docker Compose
docker compose -f ../docker-compose.csharp.yml up -d
```
