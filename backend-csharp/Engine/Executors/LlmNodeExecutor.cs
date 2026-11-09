using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// LLM 大语言模型对话与输出生成节点。
/// </summary>
public class LlmNodeExecutor : INodeExecutor
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly CredentialEncryptionService _encryption;
    private readonly OrdoDbContext _db;

    public LlmNodeExecutor(IHttpClientFactory httpClientFactory, CredentialEncryptionService encryption, OrdoDbContext db)
    {
        _httpClientFactory = httpClientFactory;
        _encryption = encryption;
        _db = db;
    }

    public string NodeType => "llm";

    public async Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        string prompt = WorkflowValueEvaluator.ResolveVariables(node.Config.TryGetValue("prompt", out var p) ? p : null, context)?.ToString() ?? "";
        string model = node.Config.TryGetValue("model", out var m) ? m?.ToString() ?? "gpt-4o" : "gpt-4o";

        // 查询绑定的模型供应商
        string? providerId = node.Config.TryGetValue("provider_id", out var pid) ? pid?.ToString() : null;
        string baseUrl = "https://api.openai.com/v1";
        string apiKey = "";

        if (!string.IsNullOrEmpty(providerId))
        {
            var provider = await _db.ModelProviders.FindAsync(new object[] { providerId }, ct);
            if (provider != null)
            {
                baseUrl = provider.BaseUrl.TrimEnd('/');
                apiKey = _encryption.Decrypt(provider.EncryptedApiKey);
                if (string.IsNullOrEmpty(model) && !string.IsNullOrEmpty(provider.DefaultModel))
                {
                    model = provider.DefaultModel;
                }
            }
        }

        var client = _httpClientFactory.CreateClient();
        client.Timeout = TimeSpan.FromMinutes(3);

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/chat/completions");
        if (!string.IsNullOrEmpty(apiKey))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        }

        var requestBody = new
        {
            model = model,
            messages = new[]
            {
                new { role = "user", content = prompt }
            }
        };

        request.Content = new StringContent(JsonSerializer.Serialize(requestBody), Encoding.UTF8, "application/json");

        var response = await client.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        string json = await response.Content.ReadAsStringAsync(ct);
        using var doc = JsonDocument.Parse(json);
        string reply = doc.RootElement
            .GetProperty("choices")[0]
            .GetProperty("message")
            .GetProperty("content")
            .GetString() ?? "";

        return new Dictionary<string, object?>
        {
            { "text", reply },
            { "output", reply }
        };
    }
}
