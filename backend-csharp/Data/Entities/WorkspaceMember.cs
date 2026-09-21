using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作区成员关系实体。
/// 对应数据库表：workspace_members
/// </summary>
[Table("workspace_members")]
public class WorkspaceMember
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
    [Column("user_id")]
    [MaxLength(36)]
    public string UserId { get; set; } = string.Empty;

    [Required]
    [Column("role")]
    [MaxLength(20)]
    public string Role { get; set; } = "viewer";

    [Column("joined_at")]
    public DateTime JoinedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(UserId))]
    public virtual User? User { get; set; }

    [ForeignKey(nameof(WorkspaceId))]
    public virtual Workspace? Workspace { get; set; }
}
