using System.Threading.Channels;

namespace Ordo.Backend.Background;

/// <summary>
/// 工作流后台执行任务载荷。
/// </summary>
public record WorkflowExecutionMessage(string RunId, string? ApprovalId = null);

/// <summary>
/// 负责进程内工作流并发排队的 Channel 队列。
/// </summary>
public class WorkflowQueue
{
    private readonly Channel<WorkflowExecutionMessage> _channel = Channel.CreateUnbounded<WorkflowExecutionMessage>(new UnboundedChannelOptions
    {
        SingleReader = false,
        SingleWriter = false
    });

    /// <summary>
    /// 将一个工作流执行请求投递到后台队列。
    /// </summary>
    public ValueTask EnqueueAsync(string runId, string? approvalId = null, CancellationToken ct = default)
    {
        return _channel.Writer.WriteAsync(new WorkflowExecutionMessage(runId, approvalId), ct);
    }

    /// <summary>
    /// 从队列读取任务。
    /// </summary>
    public IAsyncEnumerable<WorkflowExecutionMessage> ReadAllAsync(CancellationToken ct = default)
    {
        return _channel.Reader.ReadAllAsync(ct);
    }
}
