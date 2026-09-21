using Ordo.Backend.Engine.Models;

namespace Ordo.Backend.Engine;

/// <summary>
/// 工作流节点执行器契约。
/// </summary>
public interface INodeExecutor
{
    /// <summary>
    /// 支持的节点类型标识（如 "start", "end", "llm", "host_info", "rdp_disconnect" 等）。
    /// </summary>
    string NodeType { get; }

    /// <summary>
    /// 执行单个节点。
    /// </summary>
    /// <param name="node">当前节点元数据。</param>
    /// <param name="context">当前工作流全局数据上下文。</param>
    /// <param name="ct">任务取消凭据。</param>
    /// <returns>节点的输出结果。</returns>
    Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct);
}
