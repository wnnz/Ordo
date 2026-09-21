using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作流发布版本实体。
/// 对应数据库表：workflow_versions
/// </summary>
[Table("workflow_versions")]
public class WorkflowVersion
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

    [Column("version")]
    public int Version { get; set; }

    [Required]
    [Column("graph", TypeName = "json")]
    public string Graph { get; set; } = "{}";

    [Column("resolved_references", TypeName = "json")]
    public string ResolvedReferences { get; set; } = "{}";

    [Column("change_note")]
    public string ChangeNote { get; set; } = string.Empty;

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkflowId))]
    public virtual Workflow? Workflow { get; set; }
}
