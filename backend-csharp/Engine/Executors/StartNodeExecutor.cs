using Ordo.Backend.Engine.Models;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// Start 开始节点执行器：将外部传入的初始输入映射到上下文。
/// </summary>
public class StartNodeExecutor : INodeExecutor
{
    public string NodeType => "start";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        object? inputs = context.TryGetValue("inputs", out var val) ? val : new Dictionary<string, object?>();
        return Task.FromResult(inputs);
    }
}
