using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.Engine;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Services;

namespace Ordo.Backend.Background;

/// <summary>
/// 后台工作流队列消费服务（单体 Worker）。
/// </summary>
public class WorkflowQueueProcessor : BackgroundService
{
    private readonly WorkflowQueue _queue;
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<WorkflowQueueProcessor> _logger;

    private static readonly JsonSerializerOptions SafeJsonOptions = new()
    {
        ReferenceHandler = System.Text.Json.Serialization.ReferenceHandler.IgnoreCycles
    };

    public WorkflowQueueProcessor(
        WorkflowQueue queue,
        IServiceProvider serviceProvider,
        ILogger<WorkflowQueueProcessor> logger)
    {
        _queue = queue;
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Ordo C# Workflow Queue Processor started.");

        await foreach (var message in _queue.ReadAllAsync(stoppingToken))
        {
            try
            {
                await ProcessRunAsync(message.RunId, message.ApprovalId, stoppingToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error processing workflow run {RunId}", message.RunId);
            }
        }
    }

    private async Task ProcessRunAsync(string runId, string? approvalId, CancellationToken ct)
    {
        using var scope = _serviceProvider.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrdoDbContext>();
        var engine = scope.ServiceProvider.GetRequiredService<WorkflowEngine>();
        var eventsService = scope.ServiceProvider.GetRequiredService<RunEventsService>();

        var run = await db.WorkflowRuns.FirstOrDefaultAsync(r => r.Id == runId, ct);
        if (run == null)
        {
            _logger.LogWarning("Workflow run {RunId} not found.", runId);
            return;
        }

        run.Status = "running";
        run.StartedAt ??= DateTime.UtcNow;
        await db.SaveChangesAsync(ct);

        WorkflowGraph graph;
        try
        {
            graph = JsonSerializer.Deserialize<WorkflowGraph>(run.ExecutionGraph) ?? new WorkflowGraph();
        }
        catch (Exception ex)
        {
            run.Status = "failed";
            run.Error = $"Failed to parse execution graph: {ex.Message}";
            run.FinishedAt = DateTime.UtcNow;
            await db.SaveChangesAsync(ct);
            return;
        }

        Dictionary<string, object?> inputs = new();
        try
        {
            inputs = JsonSerializer.Deserialize<Dictionary<string, object?>>(run.Inputs) ?? new();
        }
        catch { }

        // 如果存在审批恢复响应，放入输入上下文
        if (!string.IsNullOrEmpty(approvalId))
        {
            var approval = await db.WorkflowApprovals.FirstOrDefaultAsync(a => a.Id == approvalId, ct);
            if (approval != null)
            {
                inputs[$"__approval_response_{approval.NodeId}"] = JsonSerializer.Deserialize<Dictionary<string, object?>>(approval.Response);
            }
        }

        var (status, outputs, trace, error, pause) = await engine.ExecuteGraphAsync(runId, graph, inputs, ct);

        run.Status = status;
        run.Outputs = JsonSerializer.Serialize(outputs, SafeJsonOptions);
        run.Trace = JsonSerializer.Serialize(trace, SafeJsonOptions);
        run.Error = error;

        if (status == "waiting" && pause != null)
        {
            // 创建审批等待记录
            var approvalRecord = new WorkflowApproval
            {
                WorkspaceId = run.WorkspaceId,
                WorkflowId = run.WorkflowId,
                RunId = run.Id,
                NodeId = pause.NodeId,
                Status = "pending",
                Request = JsonSerializer.Serialize(pause.RequestData, SafeJsonOptions),
                ResumeState = JsonSerializer.Serialize(pause.ResumeState, SafeJsonOptions)
            };
            db.WorkflowApprovals.Add(approvalRecord);
        }
        else
        {
            run.FinishedAt = DateTime.UtcNow;
        }

        await db.SaveChangesAsync(ct);
    }
}
