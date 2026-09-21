using System.Text;
using System.Text.Json;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 远程桌面会话安全断开节点。
/// </summary>
public class RdpDisconnectNodeExecutor : INodeExecutor
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly OrdoSettings _settings;

    public RdpDisconnectNodeExecutor(IHttpClientFactory httpClientFactory, OrdoSettings settings)
    {
        _httpClientFactory = httpClientFactory;
        _settings = settings;
    }

    public string NodeType => "rdp_disconnect";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        string token = !string.IsNullOrWhiteSpace(_settings.HostInfoAgentToken)
            ? _settings.HostInfoAgentToken
            : _settings.SandboxSharedSecret;

        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_settings.HostInfoAgentUrl.TrimEnd('/')}/v1/rdp/disconnect");
        request.Headers.Add("X-Ordo-Host-Token", token);

        var body = new Dictionary<string, object?>();
        if (node.Data.TryGetValue("session_id", out var sid) && sid != null)
        {
            object? resolvedSid = WorkflowValueEvaluator.ResolveVariables(sid, context);
            if (int.TryParse(resolvedSid?.ToString(), out int idVal) && idVal > 0)
            {
                body["session_id"] = idVal;
            }
        }

        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

        var response = await client.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        string json = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
    }
}
