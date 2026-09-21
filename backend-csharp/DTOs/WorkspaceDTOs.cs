using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class WorkspaceCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("timezone")]
    public string Timezone { get; set; } = "UTC";
}

public class WorkspaceUpdateRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("icon")]
    public string? Icon { get; set; }

    [JsonPropertyName("timezone")]
    public string? Timezone { get; set; }

    [JsonPropertyName("version")]
    public int Version { get; set; }
}

public class WorkspaceResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("slug")]
    public string Slug { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("icon")]
    public string? Icon { get; set; }

    [JsonPropertyName("timezone")]
    public string Timezone { get; set; } = "UTC";

    [JsonPropertyName("is_archived")]
    public bool IsArchived { get; set; }

    [JsonPropertyName("role")]
    public string Role { get; set; } = "viewer";

    [JsonPropertyName("version")]
    public int Version { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class WorkspaceMemberResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("workspace_id")]
    public string WorkspaceId { get; set; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; set; } = "viewer";

    [JsonPropertyName("joined_at")]
    public DateTime JoinedAt { get; set; }

    [JsonPropertyName("user")]
    public UserResponse? User { get; set; }
}
