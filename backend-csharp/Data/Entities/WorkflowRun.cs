using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作流执行记录实体。
/// 对应数据库表：workflow_runs
/// </summary>
[Table("workflow_runs")]
public class WorkflowRun
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("workspace_id")]
    [MaxLength(36)]
    public string WorkspaceId { get; set; } = string.Empty;

    [Required]
    [Column("workflow_id")]
    [MaxLength(36)]
    public string WorkflowId { get; set; } = string.Empty;

    [Column("workflow_version_id")]
    [MaxLength(36)]
    public string? WorkflowVersionId { get; set; }

    [Required]
    [Column("status")]
    [MaxLength(30)]
    public string Status { get; set; } = "pending";

    [Required]
    [Column("triggered_by")]
    [MaxLength(40)]
    public string TriggeredBy { get; set; } = "studio";

    [Column("trigger_user_id")]
    [MaxLength(255)]
    public string? TriggerUserId { get; set; }

    [Column("inputs", TypeName = "json")]
    public string Inputs { get; set; } = "{}";

    [Column("execution_graph", TypeName = "json")]
    public string ExecutionGraph { get; set; } = "{}";

    [Column("outputs", TypeName = "json")]
    public string Outputs { get; set; } = "{}";

    [Column("trace", TypeName = "json")]
    public string Trace { get; set; } = "[]";

    [Column("error")]
    public string? Error { get; set; }

    [Column("task_id")]
    [MaxLength(36)]
    public string? TaskId { get; set; }

    [Column("attempt_count")]
    public int AttemptCount { get; set; } = 0;

    [Column("retry_of_run_id")]
    [MaxLength(36)]
    public string? RetryOfRunId { get; set; }

    [Column("idempotency_key")]
    [MaxLength(128)]
    public string? IdempotencyKey { get; set; }

    [Column("request_fingerprint")]
    [MaxLength(64)]
    public string? RequestFingerprint { get; set; }

    [Column("lease_token")]
    [MaxLength(36)]
    public string? LeaseToken { get; set; }

    [Column("lease_expires_at")]
    public DateTime? LeaseExpiresAt { get; set; }

    [Column("started_at")]
    public DateTime? StartedAt { get; set; }

    [Column("cancel_requested_at")]
    public DateTime? CancelRequestedAt { get; set; }

    [Column("created_by")]
    [MaxLength(36)]
    public string? CreatedBy { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("finished_at")]
    public DateTime? FinishedAt { get; set; }

    [ForeignKey(nameof(WorkflowId))]
    public virtual Workflow? Workflow { get; set; }
}
