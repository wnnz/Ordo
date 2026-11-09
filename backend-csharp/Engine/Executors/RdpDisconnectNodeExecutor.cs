using System.Text.Json;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;
using Ordo.Backend.HostOps;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 远程桌面会话安全断开节点（进程内直调 WTS API）。
/// </summary>
public class RdpDisconnectNodeExecutor : INodeExecutor
{
    public string NodeType => "rdp_disconnect";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        int? sessionId = null;
        if (node.Config.TryGetValue("session_id", out var sid) && sid != null)
        {
            object? resolvedSid = WorkflowValueEvaluator.ResolveVariables(sid, context);
            if (int.TryParse(resolvedSid?.ToString(), out int idVal) && idVal > 0)
            {
                sessionId = idVal;
            }
        }

        var result = RdpManager.DisconnectSessions(sessionId);
        string json = JsonSerializer.Serialize(result);
        object? output = JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
        return Task.FromResult(output);
    }
}
