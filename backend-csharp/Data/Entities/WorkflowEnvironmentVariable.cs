using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 工作流环境变量实体。
/// 对应数据库表：workflow_environment_variables
/// </summary>
[Table("workflow_environment_variables")]
public class WorkflowEnvironmentVariable
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
    [Column("name")]
    [MaxLength(80)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("value_type")]
    [MaxLength(16)]
    public string ValueType { get; set; } = "string";

    [Required]
    [Column("encrypted_value")]
    public string EncryptedValue { get; set; } = string.Empty;

    [Column("description")]
    [MaxLength(500)]
    public string Description { get; set; } = string.Empty;

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkflowId))]
    public virtual Workflow? Workflow { get; set; }
}
