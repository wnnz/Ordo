# Ordo C# (.NET 10) 单体后端

Ordo AI 工作流平台的高性能 C# 原生后端工程，可直接作为 Windows 服务运行。

## 架构亮点

1. **单体聚合架构（Monolithic Convergence）**：
   - 移除原有的 Celery Worker、Celery Beat 与 Redis 容器。
   - API 接入、Channel 任务排队、BackgroundService 队列消费与定时工作流调度统一合并在一个轻量 .NET 进程内。
2. **内嵌宿主机插件（原 OrdoWindowsAgent）**：
   - `HostOps/` 目录内置了主机网卡采集（`HostInfoCollector`）与 RDP 会话管理（`RdpManager`）。
   - `host_info` / `rdp_disconnect` 节点直接进程内调用 `iphlpapi.dll` / `wtsapi32.dll`，不再依赖独立的 Agent HTTP 服务。
3. **内嵌 Python 沙箱控制面（原 sandbox 服务）**：
   - `Sandbox/SandboxExecutionService` 通过 Docker.DotNet 直连 Docker Desktop（`npipe://./pipe/docker_engine`）。
   - 每次执行创建一次性受限容器（`ordo-sandbox` 镜像）：非 root、无 capabilities、只读注入、tmpfs `/tmp`、PID/内存/CPU 限制、默认禁网。
   - 不再有独立的 sandbox FastAPI 服务，隔离模型不变。
4. **单端口交付 Web + API**：`frontend/dist` 在发布时链接至 `wwwroot` 一并输出，SPA 路由自动回退。
5. **原生 Windows 服务**：`UseWindowsService` 协同 SCM，LocalSystem 身份运行（RDP 断开会话需要 SYSTEM 权限），控制台模式不受影响。
6. **100% 兼容现有 PostgreSQL 数据**：EF Core + Npgsql、Argon2id 密码哈希、Fernet 凭据加解密。

## 目录组织

- `Data/`：EF Core 数据库上下文与 19 个独立数据实体。
- `Common/`：`Security/`（FernetCryptography、Argon2id、JWT）、`Configuration/`（环境变量绑定）、`Auth/`。
- `Engine/`：DAG 工作流图校验、拓扑执行、变量解析与各节点执行器。
- `HostOps/`：宿主机操作插件（网卡采集、RDP 会话枚举/断开、WTS/IPHLPAPI P/Invoke）。
- `Sandbox/`：进程内 Docker 沙箱控制面（tar 注入、日志流、产物回收、限额校验）。
- `Background/`：基于 `Channel<T>` 的异步 Worker 消费与定时调度器。
- `Controllers/`：管理端与公开应用端标准 Web API。
- `Services/`：进程内事件发布流（SSE 流式推流）。

## Windows 服务部署（推荐）

```powershell
# 一键安装/更新（自动发布 win-x64 自包含、写入服务环境变量、注册并启动 OrdoBackend 服务）
.\scripts\install-windows-service.ps1 -BuildFrontend

# 卸载服务（保留程序与数据目录）
.\scripts\install-windows-service.ps1 -Uninstall
```

脚本行为：

- 发布到 `backend-csharp\bin\publish-win`，复制到 `D:\Program Files\Ordo\backend`。
- 数据目录 `D:\Program Files\Ordo\data\files` 与 `...\sandbox-artifacts`。
- 服务级环境变量写入 `HKLM:\SYSTEM\CurrentControlSet\Services\OrdoBackend\Environment`：
  `DATABASE_URL`、`APP_SECRET_KEY`、`CREDENTIAL_ENCRYPTION_KEY`、`STORAGE_PATH`、
  `SANDBOX_ARTIFACT_PATH`、`CORS_ORIGINS`、`ORDO_BIND_ADDRESS`、`ORDO_PORT`、`DOCKER_HOST`。
- `DATABASE_URL` 默认把 `.env` 中的 `shared-postgres`/`postgres` 主机名改写为 `127.0.0.1:55432`
  （Docker `shared-postgres` 的宿主映射端口），也可用 `-DatabaseUrl` 显式覆盖。
- `ordo-sandbox` 镜像缺失时自动 `docker build -t ordo-sandbox ./sandbox`。
- 服务以 LocalSystem 运行，失败自动重启（5s/15s/60s 阶梯）。

前置条件：Docker Desktop 运行中（数据库 + 沙箱运行时容器），`shared-postgres` 已启动并发布 55432 端口。

## 域名与反向代理（ordo.mossdeck.com）

对外访问通过 **sg2 服务器**转发：`https://ordo.mossdeck.com` → `http://10.66.70.2:50008`（本机 cn1-sg2 隧道地址，`.env` 的 `ORDO_BIND_ADDRESS=10.66.70.2,10.66.69.4,127.0.0.1` 同时保留本地访问）。sg2 侧为 SNI 分流 + 回环 TLS 监听 `127.0.0.1:18515`，权威配置见 my-docker-composes 仓库 `sg2/edge/`。

- TLS 在 sg2 终止，本服务仅监听内网地址，不直接暴露公网。
- 服务已启用 `UseForwardedHeaders`，仅信任内网网段（10/8、172.16/12、192.168/16、loopback）注入的 `X-Forwarded-For/Proto/Host`，还原真实客户端地址。
- sg2 侧必须：`proxy_buffering off`（SSE 运行事件流）、传递 `X-Forwarded-Proto/Host`、放宽 `proxy_read_timeout`。参考配置见 `infra/sg2/ordo.mossdeck.com.nginx.conf`。
- `CORS_ORIGINS` 保持 `https://ordo.mossdeck.com`（同源部署下实际用不到，仅兜底）。

## 配置说明（服务环境变量）

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `ORDO_BIND_ADDRESS` / `ORDO_PORT` | 监听地址/端口（ASPNETCORE_URLS 优先） | `127.0.0.1:8000` |
| `DATABASE_URL` | PostgreSQL 连接（支持 postgresql+asyncpg:// 形式） | 本地 ordo 库 |
| `STORAGE_PATH` | 上传与生成文件目录 | `./data/files` |
| `SANDBOX_ARTIFACT_PATH` | 沙箱输出文件暂存目录 | `./data/sandbox-artifacts` |
| `DOCKER_HOST` | Docker 引擎地址 | `npipe://./pipe/docker_engine` |
| `SANDBOX_RUNTIME_IMAGE` | 脚本执行容器镜像 | `ordo-sandbox` |
| `SANDBOX_PYTHON_PATH` | 容器内 Python 命令 | `python` |
| `APP_SECRET_KEY` / `CREDENTIAL_ENCRYPTION_KEY` | 签名与凭据加密密钥 | 见 `.env` |

## 编译与测试

```powershell
# 编译与单元/集成测试（集成测试需要 Docker + ordo-sandbox 镜像，缺失自动跳过）
dotnet test ../backend-csharp.tests

# 本地开发运行（控制台模式）
dotnet run

# 手动发布 win-x64 自包含
dotnet publish -c Release -r win-x64 --self-contained true -o bin/publish-win
```

Docker Compose 方式（`docker-compose.csharp.yml`）仍可运行，但在 Windows 上推荐直接使用 Windows 服务部署。

## 与旧组件的关系

- `agents/OrdoWindowsAgent`：已内嵌为 `HostOps/`，独立 Agent 服务不再需要；保留源码供参考。
- `sandbox/`：`app.py` 控制面已用 C# 重写为 `SandboxExecutionService`；`Dockerfile` 仍用于构建 `ordo-sandbox` 运行时镜像。
