using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// API 访问密钥实体。
/// 对应数据库表：api_keys
/// </summary>
[Table("api_keys")]
public class ApiKey
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("workspace_id")]
    [MaxLength(36)]
    public string WorkspaceId { get; set; } = string.Empty;

    [Column("workflow_id")]
    [MaxLength(36)]
    public string? WorkflowId { get; set; }

    [Required]
    [Column("name")]
    [MaxLength(120)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("key_prefix")]
    [MaxLength(16)]
    public string KeyPrefix { get; set; } = string.Empty;

    [Required]
    [Column("key_hash")]
    [MaxLength(64)]
    public string KeyHash { get; set; } = string.Empty;

    [Column("last_used_at")]
    public DateTime? LastUsedAt { get; set; }

    [Column("revoked_at")]
    public DateTime? RevokedAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkspaceId))]
    public virtual Workspace? Workspace { get; set; }
}
