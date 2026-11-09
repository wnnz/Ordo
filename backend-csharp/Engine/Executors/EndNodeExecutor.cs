using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// End 结束节点执行器：计算并返回工作流的最终输出数据。
/// </summary>
public class EndNodeExecutor : INodeExecutor
{
    public string NodeType => "end";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        if (node.Config.TryGetValue("outputs", out var rawOutputs))
        {
            if (rawOutputs is IEnumerable<object?> outputList)
            {
                var dict = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
                foreach (var item in outputList)
                {
                    if (item is IDictionary<string, object?> prop)
                    {
                        string name = prop.TryGetValue("name", out var n) ? n?.ToString() ?? "" : "";
                        object? val = prop.TryGetValue("value", out var v) ? v : null;
                        dict[name] = WorkflowValueEvaluator.ResolveVariables(val, context);
                    }
                }
                return Task.FromResult<object?>(dict);
            }

            return Task.FromResult(WorkflowValueEvaluator.ResolveVariables(rawOutputs, context));
        }

        // 未配置 outputs 时，安全复制并返回用户可见输出
        var safeContext = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        foreach (var kvp in context)
        {
            if (!kvp.Key.StartsWith("__") && kvp.Key != "inputs")
            {
                safeContext[kvp.Key] = kvp.Value;
            }
        }
        return Task.FromResult<object?>(safeContext);
    }
}
