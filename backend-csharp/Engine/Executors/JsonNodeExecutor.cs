using System.Text.Json;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// JSON 结构解析节点执行器。
/// </summary>
public class JsonNodeExecutor : INodeExecutor
{
    public string NodeType => "json";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        object? raw = node.Config.TryGetValue("value", out var v) ? v : null;
        raw = WorkflowValueEvaluator.ResolveVariables(raw, context);

        if (raw is string str)
        {
            try
            {
                var parsed = JsonSerializer.Deserialize<Dictionary<string, object?>>(str);
                return Task.FromResult<object?>(parsed);
            }
            catch
            {
                return Task.FromResult<object?>(str);
            }
        }

        return Task.FromResult(raw);
    }
}
