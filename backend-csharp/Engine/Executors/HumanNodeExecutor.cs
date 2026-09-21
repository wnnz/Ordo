using Ordo.Backend.Engine.Exceptions;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 人工审批节点：触发工作流安全挂起，等待用户或外部审批响应。
/// </summary>
public class HumanNodeExecutor : INodeExecutor
{
    public string NodeType => "human";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        // 检查上下文是否已包含审批恢复响应
        string resumeKey = $"__approval_response_{node.Id}";
        if (context.TryGetValue(resumeKey, out var responseVal))
        {
            return Task.FromResult(responseVal);
        }

        // 尚未审批，抛出暂停异常通知引擎挂起
        var requestData = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        if (node.Data.TryGetValue("title", out var title))
        {
            requestData["title"] = WorkflowValueEvaluator.ResolveVariables(title, context);
        }
        if (node.Data.TryGetValue("description", out var desc))
        {
            requestData["description"] = WorkflowValueEvaluator.ResolveVariables(desc, context);
        }

        throw new WorkflowPauseException(node.Id, requestData, context);
    }
}
