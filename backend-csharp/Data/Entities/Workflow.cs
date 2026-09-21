using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作流定义实体。
/// 对应数据库表：workflows
/// </summary>
[Table("workflows")]
public class Workflow
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("workspace_id")]
    [MaxLength(36)]
    public string WorkspaceId { get; set; } = string.Empty;

    [Column("folder_id")]
    [MaxLength(36)]
    public string? FolderId { get; set; }

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

    [Required]
    [Column("app_type")]
    [MaxLength(20)]
    public string AppType { get; set; } = "workflow";

    [Column("draft_graph", TypeName = "json")]
    public string DraftGraph { get; set; } = "{}";

    [Column("draft_version")]
    public int DraftVersion { get; set; } = 1;

    [Column("published_version_id")]
    [MaxLength(36)]
    public string? PublishedVersionId { get; set; }

    [Required]
    [Column("published_access")]
    [MaxLength(20)]
    public string PublishedAccess { get; set; } = "public";

    [Column("next_run_at")]
    public DateTime? NextRunAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("deleted_at")]
    public DateTime? DeletedAt { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(FolderId))]
    public virtual WorkflowFolder? Folder { get; set; }
}
