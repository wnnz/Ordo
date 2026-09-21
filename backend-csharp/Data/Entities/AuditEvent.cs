using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 审计日志事件实体。
/// 对应数据库表：audit_events
/// </summary>
[Table("audit_events")]
public class AuditEvent
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("workspace_id")]
    [MaxLength(36)]
    public string WorkspaceId { get; set; } = string.Empty;

    [Column("actor_id")]
    [MaxLength(36)]
    public string? ActorId { get; set; }

    [Required]
    [Column("action")]
    [MaxLength(120)]
    public string Action { get; set; } = string.Empty;

    [Required]
    [Column("target_type")]
    [MaxLength(80)]
    public string TargetType { get; set; } = string.Empty;

    [Column("target_id")]
    [MaxLength(36)]
    public string? TargetId { get; set; }

    [Column("detail", TypeName = "json")]
    public string Detail { get; set; } = "{}";

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
