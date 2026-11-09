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

    /// <summary>
    /// 与现有公开应用前端兼容的访问模式字段。
    /// </summary>
    [JsonPropertyName("access")]
    public string Access { get; set; } = "public";

    /// <summary>
    /// 当前受保护应用可用的登录和密码授权方式。
    /// </summary>
    [JsonPropertyName("access_options")]
    public Dictionary<string, bool> AccessOptions { get; set; } = new();

    /// <summary>
    /// 当前发布版本号。
    /// </summary>
    [JsonPropertyName("version")]
    public int Version { get; set; }

    /// <summary>
    /// 当前发布版本启用的触发入口。
    /// </summary>
    [JsonPropertyName("triggers")]
    public List<string> Triggers { get; set; } = new();

    [JsonPropertyName("input_fields")]
    public List<object> InputFields { get; set; } = new();
}

public class AppAccessRequest
{
    [JsonPropertyName("password")]
    public string? Password { get; set; }
}

public class AppAccessResponse
{
    /// <summary>
    /// 表示当前请求已经通过公开应用授权。
    /// </summary>
    [JsonPropertyName("authorized")]
    public bool Authorized { get; set; } = true;

    /// <summary>
    /// 与 Python 基线和前端兼容的密码授权令牌。
    /// </summary>
    [JsonPropertyName("access_token")]
    public string? AccessToken { get; set; }

    /// <summary>
    /// 兼容早期 C# 客户端的令牌别名。
    /// </summary>
    [JsonPropertyName("app_token")]
    public string? AppToken { get; set; }

    /// <summary>
    /// 密码授权记录 ID。
    /// </summary>
    [JsonPropertyName("grant_id")]
    public string? GrantId { get; set; }

    /// <summary>
    /// 登录授权对应的用户 ID。
    /// </summary>
    [JsonPropertyName("user_id")]
    public string? UserId { get; set; }
}

/// <summary>
/// 与 Python 公开应用接口兼容的运行响应。
/// </summary>
public class PublicRunResponse
{
    /// <summary>
    /// 运行记录 ID。
    /// </summary>
    [JsonPropertyName("run_id")]
    public string RunId { get; set; } = string.Empty;

    /// <summary>
    /// 当前运行状态。
    /// </summary>
    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    /// <summary>
    /// 执行使用的发布版本号。
    /// </summary>
    [JsonPropertyName("version")]
    public int Version { get; set; }

    /// <summary>
    /// 已持久化的运行输出。
    /// </summary>
    [JsonPropertyName("outputs")]
    public object Outputs { get; set; } = new();

    /// <summary>
    /// 已持久化的节点执行轨迹。
    /// </summary>
    [JsonPropertyName("trace")]
    public object Trace { get; set; } = new List<object>();

    /// <summary>
    /// 运行失败信息。
    /// </summary>
    [JsonPropertyName("error")]
    public string? Error { get; set; }

    /// <summary>
    /// 运行创建时间。
    /// </summary>
    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    /// <summary>
    /// 运行结束时间。
    /// </summary>
    [JsonPropertyName("finished_at")]
    public DateTime? FinishedAt { get; set; }
}
