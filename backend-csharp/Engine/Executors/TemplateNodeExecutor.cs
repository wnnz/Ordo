using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 文本模板拼接节点执行器。
/// </summary>
public class TemplateNodeExecutor : INodeExecutor
{
    public string NodeType => "template";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        string template = node.Config.TryGetValue("template", out var t) ? t?.ToString() ?? "" : "";
        object? rendered = WorkflowValueEvaluator.ResolveVariables(template, context);

        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "result", rendered },
            { "output", rendered }
        });
    }
}
