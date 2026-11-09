using System.Text.Json.Serialization;

namespace Ordo.Backend.HostOps.Models;

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
