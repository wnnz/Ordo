using System.Text;
using System.Text.Json;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// HTTP 请求执行节点。
/// </summary>
public class HttpNodeExecutor : INodeExecutor
{
    private readonly IHttpClientFactory _httpClientFactory;

    public HttpNodeExecutor(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    public string NodeType => "http";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        string url = WorkflowValueEvaluator.ResolveVariables(node.Config.TryGetValue("url", out var u) ? u : null, context)?.ToString() ?? "";
        string method = node.Config.TryGetValue("method", out var m) ? m?.ToString()?.ToUpperInvariant() ?? "GET" : "GET";
        object? bodyObj = WorkflowValueEvaluator.ResolveVariables(node.Config.TryGetValue("body", out var b) ? b : null, context);

        var client = _httpClientFactory.CreateClient();
        var request = new HttpRequestMessage(new HttpMethod(method), url);

        if (bodyObj != null && method is "POST" or "PUT" or "PATCH")
        {
            string bodyStr = bodyObj is string s ? s : JsonSerializer.Serialize(bodyObj);
            request.Content = new StringContent(bodyStr, Encoding.UTF8, "application/json");
        }

        var response = await client.SendAsync(request, ct);
        string content = await response.Content.ReadAsStringAsync(ct);

        object? parsedBody = content;
        try
        {
            parsedBody = JsonSerializer.Deserialize<Dictionary<string, object?>>(content);
        }
        catch
        {
            // 非 JSON 响应保留字符串
        }

        return new Dictionary<string, object?>
        {
            { "status_code", (int)response.StatusCode },
            { "body", parsedBody },
            { "is_success", response.IsSuccessStatusCode }
        };
    }
}
