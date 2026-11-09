using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ordo.Backend.Engine.Models;

/// <summary>
/// 画布完整图模型。
/// </summary>
public class WorkflowGraph
{
    [JsonPropertyName("nodes")]
    public List<WorkflowNode> Nodes { get; set; } = new();

    [JsonPropertyName("edges")]
    public List<WorkflowEdge> Edges { get; set; } = new();
}

/// <summary>
/// 工作流单个节点定义。
/// </summary>
public class WorkflowNode
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("data")]
    public Dictionary<string, object?> Data { get; set; } = new();

    /// <summary>
    /// 获取标准节点配置。优先读取 <c>data.config</c>，并兼容旧版将配置直接放在 <c>data</c> 下的图。
    /// </summary>
    [JsonIgnore]
    public Dictionary<string, object?> Config
    {
        get
        {
            if (Data.TryGetValue("config", out object? rawConfig))
            {
                object? normalized = NormalizeJsonValue(rawConfig);
                if (normalized is Dictionary<string, object?> config)
                {
                    return config;
                }
            }

            return Data.ToDictionary(
                item => item.Key,
                item => NormalizeJsonValue(item.Value),
                StringComparer.Ordinal);
        }
    }

    [JsonPropertyName("parentNode")]
    public string? ParentNode { get; set; }

    /// <summary>
    /// 获取节点的显示引用名称（label）。
    /// </summary>
    public string ReferenceName => Data.TryGetValue("label", out var val) && val != null
        ? val.ToString()?.Trim() ?? string.Empty
        : string.Empty;

    /// <summary>
    /// 将 System.Text.Json 产生的 JsonElement 递归转换为执行器可稳定处理的对象树。
    /// </summary>
    /// <param name="value">待规范化的 JSON 值。</param>
    /// <returns>字典、列表或对应的标量值。</returns>
    private static object? NormalizeJsonValue(object? value)
    {
        if (value is not JsonElement element)
        {
            return value;
        }

        return element.ValueKind switch
        {
            JsonValueKind.Object => element.EnumerateObject().ToDictionary(
                property => property.Name,
                property => NormalizeJsonValue(property.Value),
                StringComparer.Ordinal),
            JsonValueKind.Array => element.EnumerateArray().Select(item => NormalizeJsonValue(item)).ToList(),
            JsonValueKind.String => element.GetString(),
            JsonValueKind.Number when element.TryGetInt64(out long integer) => integer,
            JsonValueKind.Number => element.GetDouble(),
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => null,
            _ => element.ToString()
        };
    }
}

/// <summary>
/// 节点间的连线边定义。
/// </summary>
public class WorkflowEdge
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; set; } = string.Empty;

    [JsonPropertyName("target")]
    public string Target { get; set; } = string.Empty;

    [JsonPropertyName("sourceHandle")]
    public string? SourceHandle { get; set; }

    [JsonPropertyName("targetHandle")]
    public string? TargetHandle { get; set; }
}

/// <summary>
/// 节点单步执行轨迹模型。
/// </summary>
public class NodeTraceItem
{
    [JsonPropertyName("node_id")]
    public string NodeId { get; set; } = string.Empty;

    [JsonPropertyName("node_name")]
    public string NodeName { get; set; } = string.Empty;

    [JsonPropertyName("node_type")]
    public string NodeType { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = "running";

    [JsonPropertyName("inputs")]
    public object? Inputs { get; set; }

    [JsonPropertyName("outputs")]
    public object? Outputs { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("started_at")]
    public string StartedAt { get; set; } = DateTime.UtcNow.ToString("O");

    [JsonPropertyName("finished_at")]
    public string? FinishedAt { get; set; }

    [JsonPropertyName("elapsed_ms")]
    public long ElapsedMs { get; set; }
}
