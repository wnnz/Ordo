namespace Ordo.Backend.Engine.Exceptions;

/// <summary>
/// 当工作流执行遇到需要等待外部响应（如人工审批）时抛出该异常以安全挂起状态。
/// </summary>
public class WorkflowPauseException : Exception
{
    public string NodeId { get; }
    public Dictionary<string, object?> RequestData { get; }
    public Dictionary<string, object?> ResumeState { get; }

    public WorkflowPauseException(string nodeId, Dictionary<string, object?> requestData, Dictionary<string, object?> resumeState)
        : base($"Workflow is waiting at node {nodeId}")
    {
        NodeId = nodeId;
        RequestData = requestData;
        ResumeState = resumeState;
    }
}

/// <summary>
/// 当工作流被用户或系统显式请求取消时抛出。
/// </summary>
public class WorkflowCancelledException : Exception
{
    public WorkflowCancelledException(string message = "Workflow execution cancelled.") : base(message)
    {
    }
}
