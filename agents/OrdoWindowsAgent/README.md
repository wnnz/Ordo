# OrdoWindowsAgent (C# 原生版)

轻量级 Windows 宿主机代理服务，用于向运行在 Docker/WSL2 中的 Ordo 平台提供宿主机网络拓扑采集及远程桌面 (RDP) 会话安全断开能力。

## 特性

- **原生 Windows 服务**：基于 `Microsoft.Extensions.Hosting.WindowsServices`，毫秒级响应 SCM，彻底避免 Python 宿主容易出现的启动超时（错误 1053）。
- **零环境依赖**：支持作为独立单文件发布，不依赖系统全局 Python、注册表 `PythonPath` 或虚拟环境。
- **开机全静默**：作为标准 LocalSystem Windows 服务在后台运行，开机零弹窗、零黑框。
- **高性能采集**：直接调用 Windows 原生网络和终端服务 API (`wtsapi32.dll`)，无子进程创建开销。

## API 路由契约

默认监听地址：`http://127.0.0.1:8765`

| 路由 | 请求方法 | 鉴权方式 | 说明 |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | 无需鉴权 | 服务存活健康检查 |
| `/v1/host-info` | `GET` | `X-Ordo-Host-Token` | 收集本机适配器与主 IPv4 地址 |
| `/v1/rdp-sessions` | `GET` | `X-Ordo-Host-Token` | 枚举活跃/已连接状态的 RDP 会话 |
| `/v1/rdp/disconnect` | `POST` | `X-Ordo-Host-Token` | 安全断开指定或所有活跃 RDP 会话（不注销用户） |

## 编译与发布

```powershell
# 依赖系统 .NET 8 运行时编译发布（单文件仅约 200KB）
dotnet publish -c Release -r win-x64 --no-self-contained -p:PublishSingleFile=true -o bin/publish

# 或独立自包含发布（无需目标机器安装 .NET 运行时）
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o bin/publish
```

## 服务管理命令

```powershell
# 安装/创建服务
sc.exe create OrdoWindowsAgent binPath= "C:\ProgramData\Ordo\WindowsAgent\OrdoWindowsAgent.exe" start= auto displayname= "Ordo Windows Agent"

# 启动服务
sc.exe start OrdoWindowsAgent

# 停止服务
sc.exe stop OrdoWindowsAgent

# 卸载服务
sc.exe delete OrdoWindowsAgent
```
