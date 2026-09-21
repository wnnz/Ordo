using Ordo.Backend.Engine.Models;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 等待多分支合并执行节点。
/// </summary>
public class WaitNodeExecutor : INodeExecutor
{
    public string NodeType => "wait";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "completed", true },
            { "mode", node.Data.TryGetValue("mode", out var m) ? m?.ToString() ?? "all" : "all" }
        });
    }
}
