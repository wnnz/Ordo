using System.Text;
using System.Text.Json;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// Python 脚本沙箱执行节点：向隔离的 Sandbox 容器发起安全调度。
/// </summary>
public class ScriptNodeExecutor : INodeExecutor
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly OrdoSettings _settings;

    public ScriptNodeExecutor(IHttpClientFactory httpClientFactory, OrdoSettings settings)
    {
        _httpClientFactory = httpClientFactory;
        _settings = settings;
    }

    public string NodeType => "script";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        var client = _httpClientFactory.CreateClient();

        var payload = new Dictionary<string, object?>
        {
            { "entrypoint", node.Data.TryGetValue("entrypoint", out var ep) ? ep?.ToString() ?? "main" : "main" },
            { "source_code", node.Data.TryGetValue("source_code", out var sc) ? sc?.ToString() ?? "" : "" },
            { "source_files", node.Data.TryGetValue("source_files", out var sf) ? sf : new Dictionary<string, string>() },
            { "inputs", WorkflowValueEvaluator.ResolveVariables(node.Data.TryGetValue("inputs", out var inp) ? inp : null, context) ?? new Dictionary<string, object?>() }
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_settings.SandboxUrl.TrimEnd('/')}/v1/executions");
        if (!string.IsNullOrEmpty(_settings.SandboxSharedSecret))
        {
            request.Headers.Add("X-Sandbox-Secret", _settings.SandboxSharedSecret);
        }

        request.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");

        var response = await client.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        string json = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
    }
}
