using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 变量聚合节点：聚合多个分支或分支上游的第一个非空值。
/// </summary>
public class AggregateNodeExecutor : INodeExecutor
{
    public string NodeType => "aggregate";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        object? firstNonNull = null;

        if (node.Data.TryGetValue("variables", out var vars) && vars is IEnumerable<object?> varList)
        {
            foreach (var v in varList)
            {
                var resolved = WorkflowValueEvaluator.ResolveVariables(v, context);
                if (resolved != null && !string.IsNullOrWhiteSpace(resolved.ToString()))
                {
                    firstNonNull = resolved;
                    break;
                }
            }
        }

        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "output", firstNonNull },
            { "result", firstNonNull }
        });
    }
}
