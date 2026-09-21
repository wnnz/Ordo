using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作区实体。
/// 对应数据库表：workspaces
/// </summary>
[Table("workspaces")]
public class Workspace
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("name")]
    [MaxLength(120)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("slug")]
    [MaxLength(80)]
    public string Slug { get; set; } = string.Empty;

    [Column("description")]
    public string Description { get; set; } = string.Empty;

    [Column("icon")]
    [MaxLength(255)]
    public string? Icon { get; set; }

    [Column("timezone")]
    [MaxLength(80)]
    public string Timezone { get; set; } = "UTC";

    [Column("is_archived")]
    public bool IsArchived { get; set; } = false;

    [Column("deleted_at")]
    public DateTime? DeletedAt { get; set; }

    [Column("version")]
    public int Version { get; set; } = 1;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
