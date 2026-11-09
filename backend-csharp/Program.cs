using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.FileProviders;
using Ordo.Backend.Background;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Engine;
using Ordo.Backend.Engine.Executors;
using Ordo.Backend.Sandbox;
using Ordo.Backend.Services;

var builder = WebApplication.CreateBuilder(args);

// 支持以 Windows 服务运行（控制台/开发模式下自动回退为普通进程）
builder.Host.UseWindowsService(options => options.ServiceName = "OrdoBackend");

// 1. 读取环境与配置
var settings = new OrdoSettings();
builder.Configuration.Bind(settings);

// 从系统环境变量覆盖关键配置
if (Environment.GetEnvironmentVariable("APP_ENV") is { } appEnv) settings.AppEnv = appEnv;
if (Environment.GetEnvironmentVariable("APP_SECRET_KEY") is { } secret) settings.AppSecretKey = secret;
if (Environment.GetEnvironmentVariable("CREDENTIAL_ENCRYPTION_KEY") is { } encKey) settings.CredentialEncryptionKey = encKey;
if (Environment.GetEnvironmentVariable("DATABASE_URL") is { } dbUrl) settings.DatabaseUrl = dbUrl;
if (Environment.GetEnvironmentVariable("STORAGE_PATH") is { } stPath) settings.StoragePath = stPath;
if (Environment.GetEnvironmentVariable("CORS_ORIGINS") is { } cors) settings.CorsOrigins = cors;
if (Environment.GetEnvironmentVariable("SANDBOX_ARTIFACT_PATH") is { } sbArt) settings.SandboxArtifactPath = sbArt;
if (Environment.GetEnvironmentVariable("DOCKER_HOST") is { } dockerHost) settings.DockerHost = dockerHost;
if (Environment.GetEnvironmentVariable("SANDBOX_RUNTIME_IMAGE") is { } sbImage) settings.SandboxRuntimeImage = sbImage;
if (Environment.GetEnvironmentVariable("SANDBOX_PYTHON_PATH") is { } sbPython) settings.SandboxPythonPath = sbPython;

// 绑定监听地址：ASPNETCORE_URLS/--urls 优先，其次 ORDO_BIND_ADDRESS/ORDO_PORT
// ORDO_BIND_ADDRESS 支持逗号分隔多个地址（如 "10.66.70.2,10.66.69.4,127.0.0.1"）
if (string.IsNullOrEmpty(builder.Configuration["urls"]))
{
    string bind = Environment.GetEnvironmentVariable("ORDO_BIND_ADDRESS") ?? "127.0.0.1";
    string port = Environment.GetEnvironmentVariable("ORDO_PORT") ?? "8000";
    var urls = bind.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Select(a => $"http://{a}:{port}");
    builder.WebHost.UseUrls(urls.ToArray());
}

// 将 SQLAlchemy 风格的 postgresql+asyncpg:// url 转换为 Npgsql 标准连接串
string connectionString = ConvertDatabaseUrl(settings.DatabaseUrl);

builder.Services.AddSingleton(settings);

// 2. 注册数据库上下文
builder.Services.AddDbContext<OrdoDbContext>(options =>
{
    options.UseNpgsql(connectionString);
});

// 3. 注册 HTTP 客户端工厂
builder.Services.AddHttpClient();
builder.Services.AddHttpContextAccessor();

// 4. 注册核心安全与上下文服务
builder.Services.AddSingleton<CredentialEncryptionService>();
builder.Services.AddSingleton<JwtTokenService>();
builder.Services.AddScoped<CurrentUserContext>();
builder.Services.AddScoped<WorkspaceAuthorizationService>();

// 5. 注册事件流、任务队列与进程内沙箱单例
builder.Services.AddSingleton<RunEventsService>();
builder.Services.AddSingleton<WorkflowQueue>();
builder.Services.AddSingleton<SandboxExecutionService>();

// 6. 注册各节点执行器与引擎
builder.Services.AddTransient<INodeExecutor, StartNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, EndNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, VariableNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, JsonNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, TemplateNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, ConditionNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, ListNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, AggregateNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, WaitNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, ClassifierNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, HttpNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, HostInfoNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, RdpDisconnectNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, HumanNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, ScriptNodeExecutor>();
builder.Services.AddTransient<INodeExecutor, LlmNodeExecutor>();

builder.Services.AddTransient<NodeRegistry>();
builder.Services.AddTransient<WorkflowEngine>();

// 7. 注册后台 Worker 与调度单体服务
builder.Services.AddHostedService<WorkflowQueueProcessor>();
builder.Services.AddHostedService<WorkflowSchedulerService>();

// 8. 注册 Web API 与控制器
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
        options.JsonSerializerOptions.DictionaryKeyPolicy = JsonNamingPolicy.SnakeCaseLower;
    });

// 9. 配置跨域支持
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins(settings.CorsOriginList)
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials();
    });
});

var app = builder.Build();

// 反向代理（sg2 -> 本服务）转发头：仅信任内网来源，还原真实客户端 IP/协议/Host
var forwardedOptions = new ForwardedHeadersOptions
{
    ForwardedHeaders = ForwardedHeaders.XForwardedFor |
                       ForwardedHeaders.XForwardedProto |
                       ForwardedHeaders.XForwardedHost,
};
forwardedOptions.KnownIPNetworks.Clear();
forwardedOptions.KnownProxies.Clear();
forwardedOptions.KnownIPNetworks.Add(new System.Net.IPNetwork(IPAddress.Parse("10.0.0.0"), 8));
forwardedOptions.KnownIPNetworks.Add(new System.Net.IPNetwork(IPAddress.Parse("172.16.0.0"), 12));
forwardedOptions.KnownIPNetworks.Add(new System.Net.IPNetwork(IPAddress.Parse("192.168.0.0"), 16));
forwardedOptions.KnownIPNetworks.Add(new System.Net.IPNetwork(IPAddress.Loopback, 32));
forwardedOptions.KnownIPNetworks.Add(new System.Net.IPNetwork(IPAddress.IPv6Loopback, 128));
app.UseForwardedHeaders(forwardedOptions);

// 发布目录下的前端静态产物（frontend/dist 在构建时已链接至 wwwroot）
string webRoot = Path.Combine(AppContext.BaseDirectory, "wwwroot");
string indexHtml = Path.Combine(webRoot, "index.html");
bool serveFrontend = File.Exists(indexHtml);

app.UseCors();
app.UseRouting();

if (serveFrontend)
{
    app.UseStaticFiles(new StaticFileOptions
    {
        FileProvider = new PhysicalFileProvider(webRoot),
        OnPrepareResponse = ctx =>
        {
            ctx.Context.Response.Headers.CacheControl =
                ctx.Context.Request.Path.StartsWithSegments("/assets")
                    ? "public, max-age=31536000, immutable"
                    : "no-cache, no-store, must-revalidate";
            ApplySecurityHeaders(ctx.Context.Response);
        },
    });
}

// 健康检查接口（直接匹配 /health）
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapControllers();

if (serveFrontend)
{
    // SPA 回退：非 API 的 GET 请求一律返回 index.html，其余保持 404
    app.MapFallback(async context =>
    {
        var path = context.Request.Path;
        if (HttpMethods.IsGet(context.Request.Method) &&
            !path.StartsWithSegments("/api") &&
            !path.StartsWithSegments("/v1"))
        {
            context.Response.ContentType = "text/html; charset=utf-8";
            context.Response.Headers.CacheControl = "no-cache, no-store, must-revalidate";
            ApplySecurityHeaders(context.Response);
            await context.Response.SendFileAsync(indexHtml);
            return;
        }
        context.Response.StatusCode = StatusCodes.Status404NotFound;
    });
}

app.Run();

static void ApplySecurityHeaders(HttpResponse response)
{
    var headers = response.Headers;
    headers.ContentSecurityPolicy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
    headers.XContentTypeOptions = "nosniff";
    headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
    headers.XFrameOptions = "DENY";
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()";
}

static string ConvertDatabaseUrl(string url)
{
    if (url.StartsWith("Host=", StringComparison.OrdinalIgnoreCase) ||
        url.StartsWith("Server=", StringComparison.OrdinalIgnoreCase))
    {
        return url;
    }

    try
    {
        // 去除 postgresql+asyncpg:// 前缀
        string standard = url;
        if (standard.StartsWith("postgresql+asyncpg://", StringComparison.OrdinalIgnoreCase))
        {
            standard = "postgres://" + standard["postgresql+asyncpg://".Length..];
        }
        else if (standard.StartsWith("postgresql://", StringComparison.OrdinalIgnoreCase))
        {
            standard = "postgres://" + standard["postgresql://".Length..];
        }

        var uri = new Uri(standard);
        var userInfo = uri.UserInfo.Split(':');
        string user = userInfo.Length > 0 ? userInfo[0] : "ordo";
        string pass = userInfo.Length > 1 ? userInfo[1] : "ordo";
        string host = uri.Host;
        int port = uri.Port > 0 ? uri.Port : 5432;
        string db = uri.AbsolutePath.TrimStart('/');

        return $"Host={host};Port={port};Database={db};Username={user};Password={pass}";
    }
    catch
    {
        return url;
    }
}
