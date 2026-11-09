using System.Text.Json.Serialization;

namespace Ordo.Backend.HostOps.Models;

/// <summary>
/// 断开操作失败条目。
/// </summary>
public sealed class RdpDisconnectFailure
{
    /// <summary>
    /// 失败的会话 ID。
    /// </summary>
    [JsonPropertyName("session_id")]
    public int SessionId { get; set; }

    /// <summary>
    /// 用户名。
    /// </summary>
    [JsonPropertyName("username")]
    public string Username { get; set; } = string.Empty;

    /// <summary>
    /// 会话名称。
    /// </summary>
    [JsonPropertyName("session_name")]
    public string SessionName { get; set; } = string.Empty;

    /// <summary>
    /// 状态。
    /// </summary>
    [JsonPropertyName("state")]
    public string State { get; set; } = string.Empty;

    /// <summary>
    /// 错误详情。
    /// </summary>
    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;
}
