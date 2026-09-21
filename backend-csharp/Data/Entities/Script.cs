using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// Python 脚本定义实体。
/// 对应数据库表：scripts
/// </summary>
[Table("scripts")]
public class Script
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
    [Column("name")]
    [MaxLength(120)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("slug")]
    [MaxLength(80)]
    public string Slug { get; set; } = string.Empty;

    [Column("description")]
    public string Description { get; set; } = string.Empty;

    [Column("tags", TypeName = "json")]
    public string Tags { get; set; } = "[]";

    [Column("latest_version")]
    public int LatestVersion { get; set; } = 0;

    [Column("deleted_at")]
    public DateTime? DeletedAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}
