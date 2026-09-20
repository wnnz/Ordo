using System.Text.Json.Serialization;

namespace OrdoWindowsAgent.Models;

/// <summary>
/// RDP 会话列表响应模型。
/// </summary>
public sealed class RdpSessionsResponse
{
    /// <summary>
    /// 活跃/已连接的 RDP 会话列表。
    /// </summary>
    [JsonPropertyName("sessions")]
    public List<RdpSessionInfo> Sessions { get; set; } = new();
}
