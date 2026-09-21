using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 知识库文档实体。
/// 对应数据库表：knowledge_documents
/// </summary>
[Table("knowledge_documents")]
public class KnowledgeDocument
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
    [Column("dataset_id")]
    [MaxLength(36)]
    public string DatasetId { get; set; } = string.Empty;

    [Required]
    [Column("stored_file_id")]
    [MaxLength(36)]
    public string StoredFileId { get; set; } = string.Empty;

    [Required]
    [Column("name")]
    [MaxLength(500)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("status")]
    [MaxLength(30)]
    public string Status { get; set; } = "processing";

    [Column("metadata_json", TypeName = "json")]
    public string MetadataJson { get; set; } = "{}";

    [Column("extracted_content", TypeName = "json")]
    public string ExtractedContent { get; set; } = "{}";

    [Column("error")]
    public string? Error { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
