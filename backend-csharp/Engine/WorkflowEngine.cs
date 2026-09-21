using System.Diagnostics;
using System.Text.Json;
using Ordo.Backend.Engine.Exceptions;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Services;

namespace Ordo.Backend.Engine;

/// <summary>
/// 工作流核心执行引擎，负责拓扑编排、节点调度、上下文维护与事件发布。
/// </summary>
public class WorkflowEngine
{
    private readonly NodeRegistry _registry;
    private readonly RunEventsService _eventsService;

    public WorkflowEngine(NodeRegistry registry, RunEventsService eventsService)
    {
        _registry = registry;
        _eventsService = eventsService;
    }

    /// <summary>
    /// 校验工作流草稿图。
    /// </summary>
    public void ValidateGraph(WorkflowGraph graph)
    {
        if (graph.Nodes == null || graph.Nodes.Count == 0)
        {
            throw new ArgumentException("Graph must contain at least one node.");
        }

        var startNodes = graph.Nodes.Where(n => string.Equals(n.Type, "start", StringComparison.OrdinalIgnoreCase)).ToList();
        if (startNodes.Count != 1)
        {
            throw new ArgumentException("Graph must have exactly one start node.");
        }
    }

    /// <summary>
    /// 执行整个工作流图。
    /// </summary>
    public async Task<(string Status, Dictionary<string, object?> Outputs, List<NodeTraceItem> Trace, string? Error, WorkflowPauseException? Pause)> ExecuteGraphAsync(
        string runId,
        WorkflowGraph graph,
        Dictionary<string, object?> initialInputs,
        CancellationToken ct)
    {
        ValidateGraph(graph);

        var context = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            { "inputs", initialInputs }
        };

        var traceList = new List<NodeTraceItem>();
        var startNode = graph.Nodes.First(n => string.Equals(n.Type, "start", StringComparison.OrdinalIgnoreCase));

        var executedNodeIds = new HashSet<string>();
        var queue = new Queue<WorkflowNode>();
        queue.Enqueue(startNode);

        _eventsService.PublishRunEvent(runId, new { type = "status", status = "running" });

        while (queue.Count > 0)
        {
            ct.ThrowIfCancellationRequested();
            var current = queue.Dequeue();

            if (!executedNodeIds.Add(current.Id))
            {
                continue;
            }

            var executor = _registry.GetExecutor(current.Type);
            if (executor == null)
            {
                throw new NotSupportedException($"Node type '{current.Type}' has no registered executor.");
            }

            var traceItem = new NodeTraceItem
            {
                NodeId = current.Id,
                NodeName = current.ReferenceName,
                NodeType = current.Type,
                Status = "running",
                StartedAt = DateTime.UtcNow.ToString("O")
            };

            _eventsService.PublishRunEvent(runId, new
            {
                type = "node_started",
                node_id = current.Id,
                node_type = current.Type,
                node_name = current.ReferenceName
            });

            var sw = Stopwatch.StartNew();
            try
            {
                object? output = await executor.ExecuteAsync(current, context, ct);
                sw.Stop();

                traceItem.Status = "completed";
                traceItem.Outputs = output;
                traceItem.FinishedAt = DateTime.UtcNow.ToString("O");
                traceItem.ElapsedMs = sw.ElapsedMilliseconds;
                traceList.Add(traceItem);

                // 存入上下文（以 node_id 和 label 为 key）
                context[current.Id] = output;
                if (!string.IsNullOrWhiteSpace(current.ReferenceName))
                {
                    context[current.ReferenceName] = output;
                }

                _eventsService.PublishRunEvent(runId, new
                {
                    type = "node_finished",
                    node_id = current.Id,
                    outputs = output,
                    status = "completed"
                });

                // 处理下游节点分发
                var outEdges = graph.Edges.Where(e => e.Source == current.Id).ToList();

                // 条件节点分支路由处理
                if (string.Equals(current.Type, "condition", StringComparison.OrdinalIgnoreCase) && output is IDictionary<string, object?> cDict)
                {
                    string branch = cDict.TryGetValue("branch", out var b) ? b?.ToString() ?? "true" : "true";
                    outEdges = outEdges.Where(e => string.IsNullOrEmpty(e.SourceHandle) || string.Equals(e.SourceHandle, branch, StringComparison.OrdinalIgnoreCase)).ToList();
                }

                foreach (var edge in outEdges)
                {
                    var targetNode = graph.Nodes.FirstOrDefault(n => n.Id == edge.Target);
                    if (targetNode != null && !executedNodeIds.Contains(targetNode.Id))
                    {
                        queue.Enqueue(targetNode);
                    }
                }
            }
            catch (WorkflowPauseException pauseEx)
            {
                sw.Stop();
                traceItem.Status = "waiting";
                traceItem.FinishedAt = DateTime.UtcNow.ToString("O");
                traceItem.ElapsedMs = sw.ElapsedMilliseconds;
                traceList.Add(traceItem);

                _eventsService.PublishRunEvent(runId, new
                {
                    type = "status",
                    status = "waiting",
                    node_id = current.Id
                });

                return ("waiting", new Dictionary<string, object?>(), traceList, null, pauseEx);
            }
            catch (Exception ex)
            {
                sw.Stop();
                traceItem.Status = "failed";
                traceItem.Error = ex.Message;
                traceItem.FinishedAt = DateTime.UtcNow.ToString("O");
                traceItem.ElapsedMs = sw.ElapsedMilliseconds;
                traceList.Add(traceItem);

                _eventsService.PublishRunEvent(runId, new
                {
                    type = "status",
                    status = "failed",
                    error = ex.Message
                });

                return ("failed", new Dictionary<string, object?>(), traceList, ex.Message, null);
            }
        }

        // 提取 End 节点输出或全部输出
        var endNode = graph.Nodes.FirstOrDefault(n => string.Equals(n.Type, "end", StringComparison.OrdinalIgnoreCase));
        var finalOutputs = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);

        if (endNode != null && context.TryGetValue(endNode.Id, out var endOutput) && endOutput is IDictionary<string, object?> endDict)
        {
            foreach (var kvp in endDict) finalOutputs[kvp.Key] = kvp.Value;
        }
        else
        {
            foreach (var kvp in context)
            {
                if (!kvp.Key.StartsWith("__"))
                {
                    finalOutputs[kvp.Key] = kvp.Value;
                }
            }
        }

        _eventsService.PublishRunEvent(runId, new
        {
            type = "run_finished",
            status = "succeeded",
            outputs = finalOutputs
        });

        return ("succeeded", finalOutputs, traceList, null, null);
    }
}
