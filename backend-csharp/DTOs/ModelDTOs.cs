using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class ModelProviderCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("provider_type")]
    public string ProviderType { get; set; } = "openai-compatible";

    [JsonPropertyName("base_url")]
    public string BaseUrl { get; set; } = string.Empty;

    [JsonPropertyName("api_key")]
    public string ApiKey { get; set; } = string.Empty;

    [JsonPropertyName("default_model")]
    public string DefaultModel { get; set; } = string.Empty;

    [JsonPropertyName("config")]
    public object? Config { get; set; }
}

public class ModelProviderResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("workspace_id")]
    public string WorkspaceId { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("provider_type")]
    public string ProviderType { get; set; } = "openai-compatible";

    [JsonPropertyName("base_url")]
    public string BaseUrl { get; set; } = string.Empty;

    [JsonPropertyName("default_model")]
    public string DefaultModel { get; set; } = string.Empty;

    [JsonPropertyName("config")]
    public object Config { get; set; } = new();

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}
