using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 系统级全局设置实体。
/// 对应数据库表：system_settings
/// </summary>
[Table("system_settings")]
public class SystemSetting
{
    [Key]
    [Column("key")]
    [MaxLength(80)]
    public string Key { get; set; } = string.Empty;

    [Required]
    [Column("value", TypeName = "json")]
    public string Value { get; set; } = "{}";

    [Column("updated_by")]
    [MaxLength(36)]
    public string? UpdatedBy { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}
