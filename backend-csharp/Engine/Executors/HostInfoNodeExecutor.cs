using System.Text.Json;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.HostOps;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 宿主机网卡与主 IP 探测节点（进程内直调 Windows 原生 API）。
/// </summary>
public class HostInfoNodeExecutor : INodeExecutor
{
    public string NodeType => "host_info";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        var result = HostInfoCollector.Collect();
        string json = JsonSerializer.Serialize(result);
        object? output = JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
        return Task.FromResult(output);
    }
}
