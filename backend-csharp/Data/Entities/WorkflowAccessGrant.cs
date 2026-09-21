using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 公开应用访问授权实体。
/// 对应数据库表：workflow_access_grants
/// </summary>
[Table("workflow_access_grants")]
public class WorkflowAccessGrant
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
    [Column("grant_type")]
    [MaxLength(20)]
    public string GrantType { get; set; } = string.Empty;

    [Column("user_id")]
    [MaxLength(36)]
    public string? UserId { get; set; }

    [Column("label")]
    [MaxLength(120)]
    public string Label { get; set; } = string.Empty;

    [Column("password_hash")]
    public string? PasswordHash { get; set; }

    [Column("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkflowId))]
    public virtual Workflow? Workflow { get; set; }
}
