using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class PublicAppMetaResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("slug")]
    public string Slug { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("app_type")]
    public string AppType { get; set; } = "workflow";

    [JsonPropertyName("published_access")]
    public string PublishedAccess { get; set; } = "public";

    [JsonPropertyName("input_fields")]
    public List<object> InputFields { get; set; } = new();
}

public class AppAccessRequest
{
    [JsonPropertyName("password")]
    public string Password { get; set; } = string.Empty;
}

public class AppAccessResponse
{
    [JsonPropertyName("app_token")]
    public string AppToken { get; set; } = string.Empty;
}
