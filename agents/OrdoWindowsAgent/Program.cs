using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using OrdoWindowsAgent.Models;
using OrdoWindowsAgent.Services;

namespace OrdoWindowsAgent;

/// <summary>
/// 应用程序入口与 HTTP 路由配置。
/// </summary>
public static class Program
{
    private const string ServiceName = "OrdoWindowsAgent";
    private static readonly string DefaultConfigPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "Ordo",
        "windows-agent.json");

    /// <summary>
    /// 主入口方法。
    /// </summary>
    /// <param name="args">命令行启动参数。</param>
    public static async Task Main(string[] args)
    {
        var config = LoadConfiguration(args);

        var builder = WebApplication.CreateBuilder(args);

        // 注册 Windows Service 支持，服务模式下自动协同 SCM
        builder.Host.UseWindowsService(options =>
        {
            options.ServiceName = ServiceName;
        });

        // 绑定监听地址
        builder.WebHost.UseUrls($"http://{config.Host}:{config.Port}");

        var app = builder.Build();

        // 统一鉴权验证本地方法
        bool IsAuthorized(HttpRequest request)
        {
            if (string.IsNullOrEmpty(config.Token))
            {
                return false;
            }

            if (!request.Headers.TryGetValue("X-Ordo-Host-Token", out var headerValues))
            {
                return false;
            }

            string supplied = headerValues.ToString();
            byte[] a = Encoding.UTF8.GetBytes(supplied);
            byte[] b = Encoding.UTF8.GetBytes(config.Token);

            return CryptographicOperations.FixedTimeEquals(a, b);
        }

        // 健康检查端点（无需鉴权）
        app.MapGet("/health", () => Results.Ok(new Dictionary<string, string>
        {
            { "status", "ok" },
            { "service", ServiceName }
        }));

        // 主机网络适配器信息端点
        app.MapGet("/v1/host-info", (HttpRequest request) =>
        {
            if (!IsAuthorized(request))
            {
                return Results.Json(new ErrorResponse { Error = "unauthorized" }, statusCode: StatusCodes.Status401Unauthorized);
            }

            try
            {
                var result = HostInfoCollector.Collect();
                return Results.Ok(result);
            }
            catch (Exception ex)
            {
                return Results.Json(new ErrorResponse { Error = "operation_failed", Detail = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
            }
        });

        // RDP 活跃会话查询端点
        app.MapGet("/v1/rdp-sessions", (HttpRequest request) =>
        {
            if (!IsAuthorized(request))
            {
                return Results.Json(new ErrorResponse { Error = "unauthorized" }, statusCode: StatusCodes.Status401Unauthorized);
            }

            try
            {
                var sessions = RdpManager.ListSessions();
                return Results.Ok(new RdpSessionsResponse { Sessions = sessions });
            }
            catch (Exception ex)
            {
                return Results.Json(new ErrorResponse { Error = "operation_failed", Detail = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
            }
        });

        // RDP 会话安全断开端点
        app.MapPost("/v1/rdp/disconnect", async (HttpRequest request) =>
        {
            if (!IsAuthorized(request))
            {
                return Results.Json(new ErrorResponse { Error = "unauthorized" }, statusCode: StatusCodes.Status401Unauthorized);
            }

            RdpDisconnectRequest? payload = null;
            if (request.ContentLength > 0)
            {
                try
                {
                    payload = await request.ReadFromJsonAsync<RdpDisconnectRequest>();
                }
                catch (Exception ex)
                {
                    return Results.Json(new ErrorResponse { Error = "invalid_request", Detail = ex.Message }, statusCode: StatusCodes.Status400BadRequest);
                }
            }

            if (payload?.SessionId.HasValue == true && payload.SessionId.Value <= 0)
            {
                return Results.Json(new ErrorResponse { Error = "invalid_request", Detail = "session_id must be a positive integer" }, statusCode: StatusCodes.Status400BadRequest);
            }

            try
            {
                var response = RdpManager.DisconnectSessions(payload?.SessionId);
                return Results.Ok(response);
            }
            catch (KeyNotFoundException ex)
            {
                return Results.Json(new ErrorResponse { Error = "session_not_found", Detail = ex.Message }, statusCode: StatusCodes.Status404NotFound);
            }
            catch (Exception ex)
            {
                return Results.Json(new ErrorResponse { Error = "operation_failed", Detail = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
            }
        });

        // 未知路径 404 处理
        app.MapFallback(() => Results.Json(new ErrorResponse { Error = "not_found" }, statusCode: StatusCodes.Status404NotFound));

        await app.RunAsync();
    }

    /// <summary>
    /// 解析命令行与环境配置。
    /// </summary>
    /// <param name="args">命令行参数。</param>
    /// <returns>配置对象。</returns>
    private static AgentConfig LoadConfiguration(string[] args)
    {
        string? configFilePath = null;
        string? overrideHost = null;
        int? overridePort = null;
        string? overrideToken = null;

        for (int i = 0; i < args.Length; i++)
        {
            if (string.Equals(args[i], "--config", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                configFilePath = args[++i];
            }
            else if (string.Equals(args[i], "--host", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                overrideHost = args[++i];
            }
            else if (string.Equals(args[i], "--port", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length && int.TryParse(args[++i], out int p))
            {
                overridePort = p;
            }
            else if (string.Equals(args[i], "--token", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                overrideToken = args[++i];
            }
        }

        string targetConfigPath = configFilePath ?? DefaultConfigPath;
        var config = new AgentConfig();

        if (File.Exists(targetConfigPath))
        {
            try
            {
                string json = File.ReadAllText(targetConfigPath);
                var parsed = JsonSerializer.Deserialize<AgentConfig>(json);
                if (parsed != null)
                {
                    config = parsed;
                }
            }
            catch
            {
                // 若读取失败则使用默认值
            }
        }

        if (string.IsNullOrWhiteSpace(config.Token))
        {
            string? envToken = Environment.GetEnvironmentVariable("ORDO_HOST_INFO_TOKEN")
                               ?? Environment.GetEnvironmentVariable("HOST_INFO_AGENT_TOKEN")
                               ?? Environment.GetEnvironmentVariable("SANDBOX_SHARED_SECRET");
            if (!string.IsNullOrWhiteSpace(envToken))
            {
                config.Token = envToken.Trim();
            }
        }

        if (!string.IsNullOrWhiteSpace(overrideHost))
        {
            config.Host = overrideHost;
        }

        if (overridePort.HasValue)
        {
            config.Port = overridePort.Value;
        }

        if (!string.IsNullOrWhiteSpace(overrideToken))
        {
            config.Token = overrideToken.Trim();
        }

        return config;
    }
}
