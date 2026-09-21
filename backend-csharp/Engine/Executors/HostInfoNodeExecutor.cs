using System.Text.Json;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Engine.Models;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 宿主机网卡与主 IP 探测节点。
/// </summary>
public class HostInfoNodeExecutor : INodeExecutor
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly OrdoSettings _settings;

    public HostInfoNodeExecutor(IHttpClientFactory httpClientFactory, OrdoSettings settings)
    {
        _httpClientFactory = httpClientFactory;
        _settings = settings;
    }

    public string NodeType => "host_info";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        string token = !string.IsNullOrWhiteSpace(_settings.HostInfoAgentToken)
            ? _settings.HostInfoAgentToken
            : _settings.SandboxSharedSecret;

        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, $"{_settings.HostInfoAgentUrl.TrimEnd('/')}/v1/host-info");
        request.Headers.Add("X-Ordo-Host-Token", token);

        var response = await client.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        string json = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
    }
}
