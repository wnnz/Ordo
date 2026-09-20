using System.Text.Json.Serialization;

namespace OrdoWindowsAgent.Models;

/// <summary>
/// 断开 RDP 会话结果。
/// </summary>
public sealed class RdpDisconnectResponse
{
    /// <summary>
    /// 是否全部成功断开。
    /// </summary>
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    /// <summary>
    /// 成功断开的会话数量。
    /// </summary>
    [JsonPropertyName("disconnected_count")]
    public int DisconnectedCount { get; set; }

    /// <summary>
    /// 成功断开的会话列表。
    /// </summary>
    [JsonPropertyName("sessions")]
    public List<RdpSessionInfo> Sessions { get; set; } = new();

    /// <summary>
    /// 断开失败的会话列表。
    /// </summary>
    [JsonPropertyName("failed")]
    public List<RdpDisconnectFailure> Failed { get; set; } = new();

    /// <summary>
    /// 结果描述信息。
    /// </summary>
    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    /// <summary>
    /// 数据来源标识。
    /// </summary>
    [JsonPropertyName("source")]
    public string Source { get; set; } = "windows-host-agent";
}
