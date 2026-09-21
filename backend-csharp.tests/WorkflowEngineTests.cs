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
}
