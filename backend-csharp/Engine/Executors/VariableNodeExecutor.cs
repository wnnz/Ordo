using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 变量赋值与聚合修改节点执行器。
/// </summary>
public class VariableNodeExecutor : INodeExecutor
{
    public string NodeType => "variable";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);

        if (node.Data.TryGetValue("assignments", out var rawAssignments) && rawAssignments is IEnumerable<object?> assignments)
        {
            foreach (var item in assignments)
            {
                if (item is not IDictionary<string, object?> assignment) continue;

                string name = assignment.TryGetValue("name", out var n) ? n?.ToString() ?? "" : "";
                string op = assignment.TryGetValue("operation", out var o) ? o?.ToString()?.ToLowerInvariant() ?? "overwrite" : "overwrite";
                object? val = WorkflowValueEvaluator.ResolveVariables(assignment.TryGetValue("value", out var v) ? v : null, context);

                if (op == "clear")
                {
                    result[name] = null;
                }
                else if (op == "append")
                {
                    var current = result.TryGetValue(name, out var cv) ? cv : null;
                    if (current is List<object?> list)
                    {
                        list.Add(val);
                    }
                    else
                    {
                        result[name] = $"{current}{val}";
                    }
                }
                else
                {
                    result[name] = val;
                }
            }
        }

        return Task.FromResult<object?>(result);
    }
}
