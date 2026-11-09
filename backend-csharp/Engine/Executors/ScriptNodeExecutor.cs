using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;
using Ordo.Backend.Sandbox;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// Python 脚本沙箱执行节点：进程内沙箱通过 Docker 创建一次性受限容器。
/// </summary>
public class ScriptNodeExecutor : INodeExecutor
{
    private readonly SandboxExecutionService _sandbox;

    public ScriptNodeExecutor(SandboxExecutionService sandbox)
    {
        _sandbox = sandbox;
    }

    public string NodeType => "script";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        var config = node.Config;
        var request = new SandboxExecuteRequest
        {
            Entrypoint = config.TryGetValue("entrypoint", out var ep) ? ep?.ToString() ?? "main" : "main",
            Source = config.TryGetValue("source", out var source)
                ? source?.ToString() ?? string.Empty
                : config.TryGetValue("source_code", out var legacySource) ? legacySource?.ToString() ?? string.Empty : string.Empty,
            SourceFiles = ConvertSourceFiles(config.TryGetValue("source_files", out var sf) ? sf : null),
            Inputs = ConvertInputs(WorkflowValueEvaluator.ResolveVariables(config.TryGetValue("inputs", out var inp) ? inp : null, context)),
            TimeoutSeconds = ConvertToInt(config.TryGetValue("timeout_seconds", out var ts) ? ts : null, 30),
            MemoryMb = ConvertToInt(config.TryGetValue("memory_mb", out var mm) ? mm : null, 256),
            NetworkEnabled = ConvertToBool(config.TryGetValue("network_enabled", out var ne) ? ne : null),
        };

        return await _sandbox.ExecuteAsync(request, ct);
    }

    private static Dictionary<string, string> ConvertSourceFiles(object? value)
    {
        var result = new Dictionary<string, string>();
        if (value is IDictionary<string, object?> dict)
        {
            foreach (var (key, item) in dict)
            {
                result[key] = item?.ToString() ?? string.Empty;
            }
        }
        else if (value is System.Text.Json.JsonElement { ValueKind: System.Text.Json.JsonValueKind.Object } el)
        {
            foreach (var prop in el.EnumerateObject())
            {
                result[prop.Name] = prop.Value.ValueKind == System.Text.Json.JsonValueKind.String
                    ? prop.Value.GetString() ?? string.Empty
                    : prop.Value.ToString();
            }
        }
        return result;
    }

    private static Dictionary<string, object?> ConvertInputs(object? value)
    {
        if (value is IDictionary<string, object?> dict)
        {
            return new Dictionary<string, object?>(dict);
        }
        if (value is System.Text.Json.JsonElement { ValueKind: System.Text.Json.JsonValueKind.Object } el)
        {
            var result = new Dictionary<string, object?>();
            foreach (var prop in el.EnumerateObject())
            {
                result[prop.Name] = prop.Value;
            }
            return result;
        }
        return new Dictionary<string, object?>();
    }

    private static int ConvertToInt(object? value, int fallback) => value switch
    {
        null => fallback,
        int i => i,
        long l => (int)l,
        double d => (int)d,
        System.Text.Json.JsonElement { ValueKind: System.Text.Json.JsonValueKind.Number } el when el.TryGetInt32(out var n) => n,
        _ => int.TryParse(value.ToString(), out var parsed) ? parsed : fallback,
    };

    private static bool ConvertToBool(object? value) => value switch
    {
        null => false,
        bool b => b,
        System.Text.Json.JsonElement { ValueKind: System.Text.Json.JsonValueKind.True } => true,
        System.Text.Json.JsonElement { ValueKind: System.Text.Json.JsonValueKind.False } => false,
        _ => bool.TryParse(value.ToString(), out var parsed) && parsed,
    };
}
