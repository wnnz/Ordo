namespace Ordo.Backend.Sandbox;

/// <summary>
/// 进程内 Python 沙箱执行请求（对齐原 sandbox 服务 /execute 载荷）。
/// </summary>
public class SandboxExecuteRequest
{
    public string? JobId { get; set; }
    public string Source { get; set; } = string.Empty;
    public Dictionary<string, string> SourceFiles { get; set; } = new();
    public string Entrypoint { get; set; } = "main";
    public Dictionary<string, object?> Inputs { get; set; } = new();
    public int TimeoutSeconds { get; set; } = 30;
    public int MemoryMb { get; set; } = 256;
    public bool NetworkEnabled { get; set; }
}
