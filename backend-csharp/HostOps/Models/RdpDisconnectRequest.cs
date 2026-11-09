using System.Text.Json.Serialization;

namespace Ordo.Backend.HostOps.Models;

/// <summary>
/// 断开 RDP 会话请求参数。
/// </summary>
public sealed class RdpDisconnectRequest
{
    /// <summary>
    /// 可选的目标会话 ID；为空表示断开所有活跃 RDP 会话。
    /// </summary>
    [JsonPropertyName("session_id")]
    public int? SessionId { get; set; }
}
