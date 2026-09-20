using System.Text.Json.Serialization;

namespace OrdoWindowsAgent;

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

/// <summary>
/// 错误响应模型。
/// </summary>
public sealed class ErrorResponse
{
    /// <summary>
    /// 错误码标识。
    /// </summary>
    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;

    /// <summary>
    /// 详细错误说明。
    /// </summary>
    [JsonPropertyName("detail")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Detail { get; set; }
}

/// <summary>
/// 主机网络适配器信息。
/// </summary>
public sealed class AdapterInfo
{
    /// <summary>
    /// 网卡显示别名。
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// IPv4 地址列表。
    /// </summary>
    [JsonPropertyName("ipv4")]
    public List<string> IPv4 { get; set; } = new();

    /// <summary>
    /// 默认网关列表。
    /// </summary>
    [JsonPropertyName("gateway")]
    public List<string> Gateway { get; set; } = new();

    /// <summary>
    /// DNS 服务器地址列表。
    /// </summary>
    [JsonPropertyName("dns")]
    public List<string> Dns { get; set; } = new();

    /// <summary>
    /// 接口跃点数。
    /// </summary>
    [JsonPropertyName("metric")]
    public int Metric { get; set; }
}

/// <summary>
/// 主机网络采集结果模型。
/// </summary>
public sealed class HostInfoResponse
{
    /// <summary>
    /// 数据来源标识。
    /// </summary>
    [JsonPropertyName("source")]
    public string Source { get; set; } = "windows-host-agent";

    /// <summary>
    /// 主 IPv4 地址。
    /// </summary>
    [JsonPropertyName("primary_ipv4")]
    public string PrimaryIPv4 { get; set; } = string.Empty;

    /// <summary>
    /// 主网卡别名。
    /// </summary>
    [JsonPropertyName("primary_interface")]
    public string PrimaryInterface { get; set; } = string.Empty;

    /// <summary>
    /// 所有检测到的网卡列表。
    /// </summary>
    [JsonPropertyName("adapters")]
    public List<AdapterInfo> Adapters { get; set; } = new();
}

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
