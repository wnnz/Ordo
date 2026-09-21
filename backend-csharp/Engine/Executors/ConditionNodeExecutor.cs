using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 条件判断分支节点执行器。
/// </summary>
public class ConditionNodeExecutor : INodeExecutor
{
    public string NodeType => "condition";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        bool matched = WorkflowValueEvaluator.EvaluateCondition(node.Data, context);
        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "result", matched },
            { "branch", matched ? "true" : "false" }
        });
    }
}
