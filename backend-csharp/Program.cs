using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Background;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Engine;
using Ordo.Backend.Engine.Executors;
using Ordo.Backend.Services;

var builder = WebApplication.CreateBuilder(args);

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
if (Environment.GetEnvironmentVariable("SANDBOX_URL") is { } sbUrl) settings.SandboxUrl = sbUrl;
if (Environment.GetEnvironmentVariable("SANDBOX_SHARED_SECRET") is { } sbSec) settings.SandboxSharedSecret = sbSec;
if (Environment.GetEnvironmentVariable("HOST_INFO_AGENT_URL") is { } hiaUrl) settings.HostInfoAgentUrl = hiaUrl;
if (Environment.GetEnvironmentVariable("HOST_INFO_AGENT_TOKEN") is { } hiaTok) settings.HostInfoAgentToken = hiaTok;

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

// 5. 注册事件流与任务队列单例
builder.Services.AddSingleton<RunEventsService>();
builder.Services.AddSingleton<WorkflowQueue>();

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

app.UseCors();
app.UseRouting();

// 健康检查接口（直接匹配 /health）
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapControllers();

app.Run();

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
