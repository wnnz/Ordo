using System.Text.Json.Serialization;

namespace Ordo.Backend.HostOps.Models;

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
