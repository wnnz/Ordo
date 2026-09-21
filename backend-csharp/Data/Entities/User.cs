using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Ordo.Backend.Data.Entities;

/// <summary>
/// 系统用户实体。
/// 对应数据库表：users
/// </summary>
[Table("users")]
public class User
{
    [Key]
    [Column("id")]
    [MaxLength(36)]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    [Required]
    [Column("email")]
    [MaxLength(320)]
    public string Email { get; set; } = string.Empty;

    [Required]
    [Column("password_hash")]
    [MaxLength(255)]
    public string PasswordHash { get; set; } = string.Empty;

    [Required]
    [Column("display_name")]
    [MaxLength(120)]
    public string DisplayName { get; set; } = string.Empty;

    [Column("is_active")]
    public bool IsActive { get; set; } = true;

    [Column("is_platform_admin")]
    public bool IsPlatformAdmin { get; set; } = false;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
