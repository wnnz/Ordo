using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作区邀请实体。
/// 对应数据库表：workspace_invitations
/// </summary>
[Table("workspace_invitations")]
public class WorkspaceInvitation
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("workspace_id")]
    [MaxLength(36)]
    public string WorkspaceId { get; set; } = string.Empty;

    [Column("email")]
    [MaxLength(320)]
    public string? Email { get; set; }

    [Required]
    [Column("token_hash")]
    [MaxLength(64)]
    public string TokenHash { get; set; } = string.Empty;

    [Required]
    [Column("role")]
    [MaxLength(20)]
    public string Role { get; set; } = "viewer";

    [Column("expires_at")]
    public DateTime ExpiresAt { get; set; }

    [Column("max_uses")]
    public int MaxUses { get; set; } = 1;

    [Column("use_count")]
    public int UseCount { get; set; } = 0;

    [Column("revoked_at")]
    public DateTime? RevokedAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
