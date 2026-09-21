using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// Python 脚本具体版本实体。
/// 对应数据库表：script_versions
/// </summary>
[Table("script_versions")]
public class ScriptVersion
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
    [Column("script_id")]
    [MaxLength(36)]
    public string ScriptId { get; set; } = string.Empty;

    [Column("version")]
    public int Version { get; set; }

    [Required]
    [Column("source_type")]
    [MaxLength(20)]
    public string SourceType { get; set; } = "python";

    [Required]
    [Column("source_code")]
    public string SourceCode { get; set; } = string.Empty;

    [Column("source_files", TypeName = "json")]
    public string SourceFiles { get; set; } = "{}";

    [Required]
    [Column("entrypoint")]
    [MaxLength(255)]
    public string Entrypoint { get; set; } = "main";

    [Column("input_schema", TypeName = "json")]
    public string InputSchema { get; set; } = "{}";

    [Column("output_schema", TypeName = "json")]
    public string OutputSchema { get; set; } = "{}";

    [Column("network_enabled")]
    public bool NetworkEnabled { get; set; } = false;

    [Required]
    [Column("content_hash")]
    [MaxLength(64)]
    public string ContentHash { get; set; } = string.Empty;

    [Column("environment_version_id")]
    [MaxLength(36)]
    public string? EnvironmentVersionId { get; set; }

    [Column("change_note")]
    public string ChangeNote { get; set; } = string.Empty;

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(ScriptId))]
    public virtual Script? Script { get; set; }
}
