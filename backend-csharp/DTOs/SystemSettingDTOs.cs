using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class SystemSettingOut
{
    [JsonPropertyName("key")]
    public string Key { get; set; } = string.Empty;

    [JsonPropertyName("value")]
    public object Value { get; set; } = null!;

    [JsonPropertyName("default")]
    public object Default { get; set; } = null!;

    [JsonPropertyName("minimum")]
    public long? Minimum { get; set; }

    [JsonPropertyName("maximum")]
    public long? Maximum { get; set; }

    [JsonPropertyName("unit")]
    public string Unit { get; set; } = string.Empty;

    [JsonPropertyName("type")]
    public string Type { get; set; } = "integer";

    [JsonPropertyName("source")]
    public string Source { get; set; } = "environment";

    [JsonPropertyName("updated_at")]
    public DateTime? UpdatedAt { get; set; }
}

public class SystemSettingsUpdateRequest
{
    [JsonPropertyName("values")]
    public Dictionary<string, object?> Values { get; set; } = new();
}
