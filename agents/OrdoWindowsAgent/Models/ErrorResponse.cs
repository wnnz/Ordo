using System.Text.Json.Serialization;

namespace OrdoWindowsAgent.Models;

/// <summary>
/// 错误响应模型。
/// </summary>
public sealed class ErrorResponse
{
    /// <summary>
    /// 错误码标识。
    /// </summary>
    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;

    /// <summary>
    /// 详细错误说明。
    /// </summary>
    [JsonPropertyName("detail")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Detail { get; set; }
}
