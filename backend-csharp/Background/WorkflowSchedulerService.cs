using System.Text.Json;
using Cronos;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;

namespace Ordo.Backend.Background;

/// <summary>
/// 后台工作流定时任务调度与租约超时自动恢复服务（替代 Celery Beat）。
/// </summary>
public class WorkflowSchedulerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly WorkflowQueue _queue;
    private readonly ILogger<WorkflowSchedulerService> _logger;

    public WorkflowSchedulerService(
        IServiceProvider serviceProvider,
        WorkflowQueue queue,
        ILogger<WorkflowSchedulerService> logger)
    {
        _serviceProvider = serviceProvider;
        _queue = queue;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Ordo C# Workflow Scheduler Service started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await CheckScheduledWorkflowsAsync(stoppingToken);
                await RecoverStaleRunsAsync(stoppingToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error occurred during workflow scheduling/recovery tick.");
            }

            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }

    private async Task CheckScheduledWorkflowsAsync(CancellationToken ct)
    {
        using var scope = _serviceProvider.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrdoDbContext>();

        var now = DateTime.UtcNow;
        var dueWorkflows = await db.Workflows
            .Where(w => w.DeletedAt == null && w.NextRunAt != null && w.NextRunAt <= now)
            .ToListAsync(ct);

        foreach (var workflow in dueWorkflows)
        {
            try
            {
                // 获取发布版本或草稿图
                string graphJson = workflow.DraftGraph;
                string? versionId = workflow.PublishedVersionId;

                if (!string.IsNullOrEmpty(versionId))
                {
                    var version = await db.WorkflowVersions.FirstOrDefaultAsync(v => v.Id == versionId, ct);
                    if (version != null)
                    {
                        graphJson = version.Graph;
                    }
                }

                // 创建运行记录
                var run = new WorkflowRun
                {
                    WorkspaceId = workflow.WorkspaceId,
                    WorkflowId = workflow.Id,
                    WorkflowVersionId = versionId,
                    Status = "pending",
                    TriggeredBy = "scheduler",
                    Inputs = "{}",
                    ExecutionGraph = graphJson
                };

                db.WorkflowRuns.Add(run);

                // 计算下一次执行时间
                workflow.NextRunAt = CalculateNextRun(graphJson, now);

                await db.SaveChangesAsync(ct);
                await _queue.EnqueueAsync(run.Id, null, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to schedule workflow {WorkflowId}", workflow.Id);
            }
        }
    }

    private static DateTime? CalculateNextRun(string graphJson, DateTime fromTime)
    {
        try
        {
            using var doc = JsonDocument.Parse(graphJson);
            if (!doc.RootElement.TryGetProperty("nodes", out var nodes)) return null;

            foreach (var node in nodes.EnumerateArray())
            {
                if (node.TryGetProperty("type", out var t) && t.GetString() == "start" &&
                    node.TryGetProperty("data", out var data) &&
                    data.TryGetProperty("schedule", out var sched) &&
                    sched.TryGetProperty("cron", out var cronElem))
                {
                    string? cronExpr = cronElem.GetString();
                    if (!string.IsNullOrWhiteSpace(cronExpr))
                    {
                        var expression = CronExpression.Parse(cronExpr.Trim());
                        return expression.GetNextOccurrence(fromTime, TimeZoneInfo.Utc);
                    }
                }
            }
        }
        catch { }

        return null;
    }

    private async Task RecoverStaleRunsAsync(CancellationToken ct)
    {
        using var scope = _serviceProvider.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrdoDbContext>();

        // 超过 10 分钟仍处于 running 的失联运行重置为 failed
        var timeoutCutoff = DateTime.UtcNow.AddMinutes(-10);
        var staleRuns = await db.WorkflowRuns
            .Where(r => r.Status == "running" && r.StartedAt != null && r.StartedAt < timeoutCutoff)
            .ToListAsync(ct);

        foreach (var run in staleRuns)
        {
            run.Status = "failed";
            run.Error = "Run timed out or worker process terminated unexpectedly.";
            run.FinishedAt = DateTime.UtcNow;
        }

        if (staleRuns.Count > 0)
        {
            await db.SaveChangesAsync(ct);
            _logger.LogWarning("Recovered {Count} stale workflow runs.", staleRuns.Count);
        }
    }
}
