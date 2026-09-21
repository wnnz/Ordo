using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class WorkflowCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("app_type")]
    public string AppType { get; set; } = "workflow";

    [JsonPropertyName("folder_id")]
    public string? FolderId { get; set; }

    [JsonPropertyName("template_id")]
    public string? TemplateId { get; set; }
}

public class WorkflowUpdateRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("folder_id")]
    public string? FolderId { get; set; }

    [JsonPropertyName("draft_graph")]
    public object? DraftGraph { get; set; }

    [JsonPropertyName("published_access")]
    public string? PublishedAccess { get; set; }
}

public class WorkflowResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("workspace_id")]
    public string WorkspaceId { get; set; } = string.Empty;

    [JsonPropertyName("folder_id")]
    public string? FolderId { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("slug")]
    public string Slug { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("app_type")]
    public string AppType { get; set; } = "workflow";

    [JsonPropertyName("draft_graph")]
    public object DraftGraph { get; set; } = new();

    [JsonPropertyName("draft_version")]
    public int DraftVersion { get; set; }

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; set; }

    [JsonPropertyName("published_access")]
    public string PublishedAccess { get; set; } = "public";

    [JsonPropertyName("next_run_at")]
    public DateTime? NextRunAt { get; set; }

    [JsonPropertyName("created_by")]
    public string CreatedBy { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class RunCreateRequest
{
    [JsonPropertyName("inputs")]
    public Dictionary<string, object?> Inputs { get; set; } = new();

    [JsonPropertyName("run_as_draft")]
    public bool RunAsDraft { get; set; } = false;

    [JsonPropertyName("idempotency_key")]
    public string? IdempotencyKey { get; set; }
}

public class RunResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("workspace_id")]
    public string WorkspaceId { get; set; } = string.Empty;

    [JsonPropertyName("workflow_id")]
    public string WorkflowId { get; set; } = string.Empty;

    [JsonPropertyName("workflow_version_id")]
    public string? WorkflowVersionId { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    [JsonPropertyName("triggered_by")]
    public string TriggeredBy { get; set; } = "studio";

    [JsonPropertyName("inputs")]
    public object Inputs { get; set; } = new();

    [JsonPropertyName("outputs")]
    public object Outputs { get; set; } = new();

    [JsonPropertyName("trace")]
    public object Trace { get; set; } = new List<object>();

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("started_at")]
    public DateTime? StartedAt { get; set; }

    [JsonPropertyName("finished_at")]
    public DateTime? FinishedAt { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class WorkflowFolderCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;
}

public class WorkflowFolderUpdateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;
}

public class WorkflowFolderMoveRequest
{
    [JsonPropertyName("folder_id")]
    public string? FolderId { get; set; }
}

public class WorkflowFolderResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("workspace_id")]
    public string WorkspaceId { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("workflow_count")]
    public int WorkflowCount { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}
