using System.Security.Cryptography;
using System.Text;
using Ordo.Backend.Common.Configuration;

namespace Ordo.Backend.Common.Security;

/// <summary>
/// 凭据与敏感环境变量统一加解密服务。
/// </summary>
public class CredentialEncryptionService
{
    private readonly string _fernetKey;

    public CredentialEncryptionService(OrdoSettings settings)
    {
        if (!string.IsNullOrWhiteSpace(settings.CredentialEncryptionKey))
        {
            string raw = settings.CredentialEncryptionKey.Trim();
            // 如果长度正好是 44 且能被 Base64 解码，则视为合法的 Fernet Key
            try
            {
                byte[] decoded = FernetCryptography.DecodeUrlSafeBase64(raw);
                if (decoded.Length == 32)
                {
                    _fernetKey = raw;
                }
                else
                {
                    _fernetKey = DeriveKeyFromSeed(raw);
                }
            }
            catch
            {
                _fernetKey = DeriveKeyFromSeed(raw);
            }
        }
        else
        {
            _fernetKey = DeriveKeyFromSeed(settings.AppSecretKey);
        }
    }

    private static string DeriveKeyFromSeed(string seed)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(seed));
        return FernetCryptography.EncodeUrlSafeBase64(hash);
    }

    /// <summary>
    /// 加密敏感凭据或密钥。
    /// </summary>
    public string Encrypt(string plainText)
    {
        if (string.IsNullOrEmpty(plainText)) return string.Empty;
        return FernetCryptography.Encrypt(plainText, _fernetKey);
    }

    /// <summary>
    /// 解密敏感凭据或密钥。
    /// </summary>
    public string Decrypt(string cipherText)
    {
        if (string.IsNullOrEmpty(cipherText)) return string.Empty;
        return FernetCryptography.Decrypt(cipherText, _fernetKey);
    }
}
