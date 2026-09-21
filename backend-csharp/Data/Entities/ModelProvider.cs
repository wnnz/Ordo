using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// AI 模型供应商配置实体。
/// 对应数据库表：model_providers
/// </summary>
[Table("model_providers")]
public class ModelProvider
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
    [Column("provider_type")]
    [MaxLength(40)]
    public string ProviderType { get; set; } = "openai-compatible";

    [Required]
    [Column("base_url")]
    [MaxLength(500)]
    public string BaseUrl { get; set; } = string.Empty;

    [Required]
    [Column("encrypted_api_key")]
    public string EncryptedApiKey { get; set; } = string.Empty;

    [Required]
    [Column("default_model")]
    [MaxLength(120)]
    public string DefaultModel { get; set; } = string.Empty;

    [Column("config", TypeName = "json")]
    public string Config { get; set; } = "{}";

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkspaceId))]
    public virtual Workspace? Workspace { get; set; }
}
