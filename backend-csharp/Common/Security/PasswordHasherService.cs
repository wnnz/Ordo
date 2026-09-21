using Isopoh.Cryptography.Argon2;

namespace Ordo.Backend.Common.Security;

/// <summary>
/// 负责基于 Argon2id 的用户密码哈希与验证服务，100% 兼容 Python passlib / argon2-cffi。
/// </summary>
public static class PasswordHasherService
{
    /// <summary>
    /// 对明文密码生成 Argon2id 哈希字符串。
    /// </summary>
    /// <param name="password">明文密码。</param>
    /// <returns>符合 PHC 格式的哈希字符串。</returns>
    public static string HashPassword(string password)
    {
        return Argon2.Hash(password);
    }

    /// <summary>
    /// 校验明文密码是否与给定的 Argon2 哈希匹配。
    /// </summary>
    /// <param name="password">明文密码。</param>
    /// <param name="hash">数据库中存储的哈希值。</param>
    /// <returns>匹配返回 true，否则 false。</returns>
    public static bool VerifyPassword(string password, string hash)
    {
        try
        {
            return Argon2.Verify(hash, password);
        }
        catch
        {
            return false;
        }
    }
}
