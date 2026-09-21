using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace Ordo.Backend.Common.Security;

/// <summary>
/// 实现 Python cryptography.fernet 标准规范的加解密工具类。
/// 用于对数据库中的凭据、敏感环境变量进行解密和加密。
/// </summary>
public static class FernetCryptography
{
    /// <summary>
    /// 使用给定的密钥加密明文。
    /// </summary>
    /// <param name="plainText">明文字符串。</param>
    /// <param name="keyString">Base64Url 编码的 32 字节密钥。</param>
    /// <returns>Base64Url 编码的 Fernet 密文字符串。</returns>
    public static string Encrypt(string plainText, string keyString)
    {
        byte[] rawKey = DecodeUrlSafeBase64(keyString);
        if (rawKey.Length != 32)
        {
            throw new ArgumentException("Fernet key must be 32 bytes.", nameof(keyString));
        }

        byte[] signingKey = rawKey[..16];
        byte[] encryptionKey = rawKey[16..];

        byte version = 0x80;
        long timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        byte[] iv = RandomNumberGenerator.GetBytes(16);

        byte[] plainBytes = Encoding.UTF8.GetBytes(plainText);
        byte[] cipherBytes;

        using (var aes = Aes.Create())
        {
            aes.Key = encryptionKey;
            aes.IV = iv;
            aes.Mode = CipherMode.CBC;
            aes.Padding = PaddingMode.PKCS7;

            using var encryptor = aes.CreateEncryptor();
            cipherBytes = encryptor.TransformFinalBlock(plainBytes, 0, plainBytes.Length);
        }

        // 拼接 version (1) + timestamp (8) + IV (16) + cipher
        byte[] payload = new byte[1 + 8 + 16 + cipherBytes.Length];
        payload[0] = version;
        BinaryPrimitives.WriteInt64BigEndian(payload.AsSpan(1, 8), timestamp);
        Buffer.BlockCopy(iv, 0, payload, 9, 16);
        Buffer.BlockCopy(cipherBytes, 0, payload, 25, cipherBytes.Length);

        // 计算 HMAC-SHA256
        using var hmac = new HMACSHA256(signingKey);
        byte[] hash = hmac.ComputeHash(payload);

        // 拼接 payload + hash
        byte[] token = new byte[payload.Length + hash.Length];
        Buffer.BlockCopy(payload, 0, token, 0, payload.Length);
        Buffer.BlockCopy(hash, 0, token, payload.Length, hash.Length);

        return EncodeUrlSafeBase64(token);
    }

    /// <summary>
    /// 使用给定的密钥解密 Fernet 密文。
    /// </summary>
    /// <param name="tokenString">Base64Url 编码的 Fernet 密文字符串。</param>
    /// <param name="keyString">Base64Url 编码的 32 字节密钥。</param>
    /// <returns>解密后的明文字符串。</returns>
    public static string Decrypt(string tokenString, string keyString)
    {
        byte[] rawKey = DecodeUrlSafeBase64(keyString);
        if (rawKey.Length != 32)
        {
            throw new ArgumentException("Fernet key must be 32 bytes.", nameof(keyString));
        }

        byte[] signingKey = rawKey[..16];
        byte[] encryptionKey = rawKey[16..];

        byte[] token = DecodeUrlSafeBase64(tokenString);
        if (token.Length < 1 + 8 + 16 + 32)
        {
            throw new CryptographicException("Invalid Fernet token length.");
        }

        int payloadLength = token.Length - 32;
        byte[] payload = token[..payloadLength];
        byte[] expectedHash = token[payloadLength..];

        using (var hmac = new HMACSHA256(signingKey))
        {
            byte[] actualHash = hmac.ComputeHash(payload);
            if (!CryptographicOperations.FixedTimeEquals(actualHash, expectedHash))
            {
                throw new CryptographicException("Fernet signature verification failed.");
            }
        }

        if (payload[0] != 0x80)
        {
            throw new CryptographicException("Unsupported Fernet version.");
        }

        byte[] iv = payload[9..25];
        byte[] cipherBytes = payload[25..];

        using (var aes = Aes.Create())
        {
            aes.Key = encryptionKey;
            aes.IV = iv;
            aes.Mode = CipherMode.CBC;
            aes.Padding = PaddingMode.PKCS7;

            using var decryptor = aes.CreateDecryptor();
            byte[] plainBytes = decryptor.TransformFinalBlock(cipherBytes, 0, cipherBytes.Length);
            return Encoding.UTF8.GetString(plainBytes);
        }
    }

    public static byte[] DecodeUrlSafeBase64(string input)
    {
        string base64 = input.Replace('-', '+').Replace('_', '/');
        switch (base64.Length % 4)
        {
            case 2: base64 += "=="; break;
            case 3: base64 += "="; break;
        }
        return Convert.FromBase64String(base64);
    }

    public static string EncodeUrlSafeBase64(byte[] input)
    {
        return Convert.ToBase64String(input)
            .Replace('+', '-')
            .Replace('/', '_')
            .TrimEnd('=');
    }
}
