using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 知识库切片实体。
/// 对应数据库表：knowledge_chunks
/// </summary>
[Table("knowledge_chunks")]
public class KnowledgeChunk
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
    [Column("document_id")]
    [MaxLength(36)]
    public string DocumentId { get; set; } = string.Empty;

    [Column("ordinal")]
    public int Ordinal { get; set; }

    [Required]
    [Column("content")]
    public string Content { get; set; } = string.Empty;

    [Column("metadata_json", TypeName = "json")]
    public string MetadataJson { get; set; } = "{}";

    [Column("embedding", TypeName = "json")]
    public string Embedding { get; set; } = "[]";
}
