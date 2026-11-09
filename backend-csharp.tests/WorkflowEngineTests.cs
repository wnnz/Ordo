using System.Text.Json;
using Ordo.Backend.Engine;
using Ordo.Backend.Engine.Executors;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Services;
using Xunit;

namespace Ordo.Backend.Tests;

public class WorkflowEngineTests
{
    [Fact]
    public async Task TestWorkflowEngineExecutesLinearGraph()
    {
        var executors = new List<INodeExecutor>
        {
            new StartNodeExecutor(),
            new TemplateNodeExecutor(),
            new ConditionNodeExecutor(),
            new EndNodeExecutor()
        };
        var registry = new NodeRegistry(executors);
        var events = new RunEventsService();
        var engine = new WorkflowEngine(registry, events);

        var graph = new WorkflowGraph
        {
            Nodes = new List<WorkflowNode>
            {
                new()
                {
                    Id = "start_1",
                    Type = "start",
                    Data = new() { { "label", "开始" } }
                },
                new()
                {
                    Id = "template_1",
                    Type = "template",
                    Data = new()
                    {
                        { "label", "模板拼接" },
                        { "template", "Hello, {{inputs.user_name}}! Welcome to Ordo." }
                    }
                },
                new()
                {
                    Id = "end_1",
                    Type = "end",
                    Data = new()
                    {
                        { "label", "结束" },
                        { "outputs", new List<object>
                            {
                                new Dictionary<string, object> { { "name", "greeting" }, { "value", "{{template_1.output}}" } }
                            }
                        }
                    }
                }
            },
            Edges = new List<WorkflowEdge>
            {
                new() { Id = "e1", Source = "start_1", Target = "template_1" },
                new() { Id = "e2", Source = "template_1", Target = "end_1" }
            }
        };

        var initialInputs = new Dictionary<string, object?>
        {
            { "user_name", "Developer" }
        };

        var (status, outputs, trace, error, pause) = await engine.ExecuteGraphAsync("test-run-1", graph, initialInputs, CancellationToken.None);

        Assert.Equal("succeeded", status);
        Assert.Null(error);
        Assert.Null(pause);
        Assert.Equal(3, trace.Count);
        Assert.True(outputs.TryGetValue("greeting", out var greeting));
        Assert.Equal("Hello, Developer! Welcome to Ordo.", greeting?.ToString());
    }

    /// <summary>
    /// 验证引擎能够直接执行前端保存的 data.config 标准图结构。
    /// </summary>
    [Fact]
    public async Task TestWorkflowEngineExecutesFrontendConfigGraph()
    {
        const string json = """
        {
          "nodes": [
            { "id": "start_1", "type": "start", "data": { "label": "开始", "config": {} } },
            { "id": "template_1", "type": "template", "data": { "label": "模板", "config": { "template": "Hello, {{inputs.user_name}}!" } } },
            { "id": "end_1", "type": "end", "data": { "label": "结束", "config": { "outputs": [{ "name": "greeting", "value": "{{template_1.output}}" }] } } }
          ],
          "edges": [
            { "id": "e1", "source": "start_1", "target": "template_1" },
            { "id": "e2", "source": "template_1", "target": "end_1" }
          ]
        }
        """;
        var graph = JsonSerializer.Deserialize<WorkflowGraph>(json) ?? throw new InvalidOperationException("Graph deserialization failed");
        var registry = new NodeRegistry(new INodeExecutor[]
        {
            new StartNodeExecutor(),
            new TemplateNodeExecutor(),
            new EndNodeExecutor()
        });
        var engine = new WorkflowEngine(registry, new RunEventsService());

        var result = await engine.ExecuteGraphAsync(
            "frontend-graph-run",
            graph,
            new Dictionary<string, object?> { ["user_name"] = "Developer" },
            CancellationToken.None);

        Assert.Equal("succeeded", result.Status);
        Assert.Equal("Hello, Developer!", result.Outputs["greeting"]?.ToString());
    }
}
