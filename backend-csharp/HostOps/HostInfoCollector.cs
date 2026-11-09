using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using Ordo.Backend.HostOps.Models;
using Ordo.Backend.HostOps.Native;

namespace Ordo.Backend.HostOps;

/// <summary>
/// 负责收集 Windows 宿主机网络适配器与主 IP 信息。
/// </summary>
public static class HostInfoCollector
{
    /// <summary>
    /// 采集本机网络适配器并计算主 IPv4 地址。
    /// </summary>
    /// <returns>主机网络配置响应模型。</returns>
    public static HostInfoResponse Collect()
    {
        var adapters = new List<AdapterInfo>();
        var indexMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        // 查询系统当前最优路由的目标接口索引（以 8.8.8.8 作为测试外网目标）
        uint bestIfIndex = 0;
        bool hasBestInterface = IpHelperNativeMethods.GetBestInterface(0x08080808, out bestIfIndex) == 0;

        foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            // 忽略非活动网卡及环回接口
            if (ni.OperationalStatus != OperationalStatus.Up || ni.NetworkInterfaceType == NetworkInterfaceType.Loopback)
            {
                continue;
            }

            var ipProps = ni.GetIPProperties();
            int ifIndex = 0;
            try
            {
                ifIndex = ipProps.GetIPv4Properties()?.Index ?? 0;
            }
            catch (NetworkInformationException)
            {
                // 网卡未绑定 IPv4 协议时 GetIPv4Properties 会抛异常，按无索引处理
            }

            var ipv4Addresses = ipProps.UnicastAddresses
                .Where(u => u.Address.AddressFamily == AddressFamily.InterNetwork)
                .Select(u => u.Address.ToString())
                .ToList();

            var gateways = ipProps.GatewayAddresses
                .Where(g => g.Address != null && g.Address.AddressFamily == AddressFamily.InterNetwork && !Equals(g.Address, IPAddress.Any))
                .Select(g => g.Address.ToString())
                .ToList();

            var dnsServers = ipProps.DnsAddresses
                .Where(d => d.AddressFamily == AddressFamily.InterNetwork)
                .Select(d => d.ToString())
                .ToList();

            indexMap[ni.Name] = ifIndex;

            adapters.Add(new AdapterInfo
            {
                Name = ni.Name,
                IPv4 = ipv4Addresses,
                Gateway = gateways,
                Dns = dnsServers,
                Metric = ifIndex
            });
        }

        // 筛选拥有有效网关且包含非本地回环/APIPA 的 IPv4 地址的候选网卡
        var candidates = adapters
            .Where(a => a.Gateway.Any(g => !string.IsNullOrWhiteSpace(g)) &&
                        a.IPv4.Any(ip => !ip.StartsWith("127.", StringComparison.Ordinal) &&
                                         !ip.StartsWith("169.254.", StringComparison.Ordinal)))
            .ToList();

        // 优先使用路由表选出的最优接口，若匹配不到则按候选列表首项回退
        AdapterInfo? primary = null;
        if (hasBestInterface)
        {
            primary = candidates.FirstOrDefault(c => indexMap.TryGetValue(c.Name, out int idx) && idx == bestIfIndex);
        }

        primary ??= candidates.FirstOrDefault();

        string primaryIpv4 = string.Empty;
        string primaryInterface = string.Empty;

        if (primary != null)
        {
            primaryInterface = primary.Name;
            primaryIpv4 = primary.IPv4.FirstOrDefault(ip =>
                !ip.StartsWith("127.", StringComparison.Ordinal) &&
                !ip.StartsWith("169.254.", StringComparison.Ordinal)) ?? string.Empty;
        }

        return new HostInfoResponse
        {
            Source = "windows-host-agent",
            PrimaryIPv4 = primaryIpv4,
            PrimaryInterface = primaryInterface,
            Adapters = adapters
        };
    }
}
