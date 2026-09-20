using System.Text.Json.Serialization;

namespace OrdoWindowsAgent.Models;

/// <summary>
/// 单个 RDP 会话信息。
/// </summary>
public sealed class RdpSessionInfo
{
    /// <summary>
    /// Windows 会话 ID。
    /// </summary>
    [JsonPropertyName("session_id")]
    public int SessionId { get; set; }

    /// <summary>
    /// 登录用户名。
    /// </summary>
    [JsonPropertyName("username")]
    public string Username { get; set; } = string.Empty;

    /// <summary>
    /// 会话名称（如 RDP-Tcp#0）。
    /// </summary>
    [JsonPropertyName("session_name")]
    public string SessionName { get; set; } = string.Empty;

    /// <summary>
    /// 会话状态（如 active、connected）。
    /// </summary>
    [JsonPropertyName("state")]
    public string State { get; set; } = string.Empty;
}
