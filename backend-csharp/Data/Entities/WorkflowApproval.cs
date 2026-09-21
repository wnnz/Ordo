using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作流人工审批节点实体。
/// 对应数据库表：workflow_approvals
/// </summary>
[Table("workflow_approvals")]
public class WorkflowApproval
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

    [Required]
    [Column("run_id")]
    [MaxLength(36)]
    public string RunId { get; set; } = string.Empty;

    [Required]
    [Column("node_id")]
    [MaxLength(120)]
    public string NodeId { get; set; } = string.Empty;

    [Required]
    [Column("status")]
    [MaxLength(30)]
    public string Status { get; set; } = "pending";

    [Column("request", TypeName = "json")]
    public string Request { get; set; } = "{}";

    [Column("response", TypeName = "json")]
    public string Response { get; set; } = "{}";

    [Column("graph", TypeName = "json")]
    public string Graph { get; set; } = "{}";

    [Column("resume_state", TypeName = "json")]
    public string ResumeState { get; set; } = "{}";

    [Column("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [Column("responded_by")]
    [MaxLength(36)]
    public string? RespondedBy { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("responded_at")]
    public DateTime? RespondedAt { get; set; }

    [ForeignKey(nameof(RunId))]
    public virtual WorkflowRun? Run { get; set; }
}
