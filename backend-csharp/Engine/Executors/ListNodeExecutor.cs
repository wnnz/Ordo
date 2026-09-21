using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 列表处理（过滤、截取、限制长度）节点。
/// </summary>
public class ListNodeExecutor : INodeExecutor
{
    public string NodeType => "list";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        object? source = WorkflowValueEvaluator.ResolveVariables(node.Data.TryGetValue("source", out var s) ? s : null, context);
        if (source is not IEnumerable<object?> list)
        {
            return Task.FromResult<object?>(new { items = Array.Empty<object>() });
        }

        var items = list.ToList();
        string op = node.Data.TryGetValue("operation", out var o) ? o?.ToString()?.ToLowerInvariant() ?? "filter" : "filter";

        if (op == "unique")
        {
            items = items.DistinctBy(x => x?.ToString()).ToList();
        }
        else if (node.Data.TryGetValue("limit", out var lim) && lim is IDictionary<string, object?> limDict)
        {
            if (limDict.TryGetValue("count", out var c) && int.TryParse(c?.ToString(), out int count))
            {
                items = items.Take(count).ToList();
            }
        }

        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "items", items },
            { "count", items.Count }
        });
    }
}
