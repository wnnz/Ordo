using System.Text.Json.Serialization;

namespace OrdoWindowsAgent.Models;

/// <summary>
/// Windows Agent 服务配置模型。
/// </summary>
public sealed class AgentConfig
{
    /// <summary>
    /// 监听主机地址，默认 127.0.0.1。
    /// </summary>
    [JsonPropertyName("host")]
    public string Host { get; set; } = "127.0.0.1";

    /// <summary>
    /// 监听端口，默认 8765。
    /// </summary>
    [JsonPropertyName("port")]
    public int Port { get; set; } = 8765;

    /// <summary>
    /// API 鉴权令牌。
    /// </summary>
    [JsonPropertyName("token")]
    public string Token { get; set; } = string.Empty;
}
