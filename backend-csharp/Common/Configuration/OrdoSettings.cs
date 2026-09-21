namespace Ordo.Backend.Common.Configuration;

/// <summary>
/// Ordo 后端系统全局配置类。
/// </summary>
public class OrdoSettings
{
    public string AppEnv { get; set; } = "development";
    public string AppSecretKey { get; set; } = "development-only-secret-change-me";
    public string? CredentialEncryptionKey { get; set; }
    public string DatabaseUrl { get; set; } = "Host=localhost;Database=ordo;Username=ordo;Password=ordo";
    public string StoragePath { get; set; } = "./data/files";
    public int AccessTokenMinutes { get; set; } = 720;
    public string CorsOrigins { get; set; } = "http://localhost:5173";
    public string SandboxUrl { get; set; } = "http://localhost:8081";
    public string SandboxSharedSecret { get; set; } = "";
    public string SandboxArtifactPath { get; set; } = "./data/sandbox-artifacts";
    public string HostInfoAgentUrl { get; set; } = "http://host.docker.internal:8765";
    public string HostInfoAgentToken { get; set; } = "";
    public long MaxUploadBytes { get; set; } = 50 * 1024 * 1024;
    public long MaxRequestBodyBytes { get; set; } = 50 * 1024 * 1024;
    public int PublicRateLimitRequests { get; set; } = 30;
    public int PublicAccessRateLimitRequests { get; set; } = 10;
    public int PublicUploadRateLimitRequests { get; set; } = 10;
    public int PublicRateLimitWindowSeconds { get; set; } = 60;
    public int PublicMaxActiveRunsPerApp { get; set; } = 10;
    public int WorkflowRunLeaseSeconds { get; set; } = 120;
    public int WorkflowPendingRecoverySeconds { get; set; } = 60;
    public int FileUploadRetentionHours { get; set; } = 24;
    public int FileOutputRetentionDays { get; set; } = 30;
    public int FileOrphanGraceHours { get; set; } = 24;
    public int FileCleanupBatchSize { get; set; } = 500;
    public bool DisableUserRegistration { get; set; } = false;
    public string LogLevel { get; set; } = "INFO";

    /// <summary>
    /// 解析后的 CORS 允许源列表。
    /// </summary>
    public string[] CorsOriginList => CorsOrigins
        .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
