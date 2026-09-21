using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 持久化文件元数据实体。
/// 对应数据库表：stored_files
/// </summary>
[Table("stored_files")]
public class StoredFile
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
    [Column("object_key")]
    [MaxLength(1000)]
    public string ObjectKey { get; set; } = string.Empty;

    [Required]
    [Column("filename")]
    [MaxLength(500)]
    public string Filename { get; set; } = string.Empty;

    [Required]
    [Column("content_type")]
    [MaxLength(200)]
    public string ContentType { get; set; } = string.Empty;

    [Column("size")]
    public int Size { get; set; }

    [Required]
    [Column("sha256")]
    [MaxLength(64)]
    public string Sha256 { get; set; } = string.Empty;

    [Required]
    [Column("purpose")]
    [MaxLength(40)]
    public string Purpose { get; set; } = "upload";

    [Column("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [Required]
    [Column("created_by")]
    [MaxLength(36)]
    public string CreatedBy { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey(nameof(WorkspaceId))]
    public virtual Workspace? Workspace { get; set; }
}
