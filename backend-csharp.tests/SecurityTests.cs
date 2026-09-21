using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Common.Security;
using Xunit;

namespace Ordo.Backend.Tests;

public class SecurityTests
{
    [Fact]
    public void TestFernetEncryptAndDecrypt()
    {
        // 验证 Python 生成的密钥和密文
        string key = "eRdaeX3K10cbIZ-4crrw7etRiqt9r2aMVuY-aArp6j8=";
        string pythonCipher = "gAAAAABqsIvFD1B_FNCY_e2eDuwBvYNboYuYBNzZRvwPiaB9EcddSWkE5uHZDcO18BdCF0w6UYm9SvgUPp3o8TLMWVuP-mpyZz_G5rbtpe3lHknXviQ0KxE=";

        string decrypted = FernetCryptography.Decrypt(pythonCipher, key);
        Assert.Equal("hello-ordo-csharp-test", decrypted);

        // 验证 C# 加密后再解密
        string plain = "csharp-generated-secret-value-123456";
        string cipher = FernetCryptography.Encrypt(plain, key);
        string roundtrip = FernetCryptography.Decrypt(cipher, key);
        Assert.Equal(plain, roundtrip);
    }

    [Fact]
    public void TestArgon2PasswordVerification()
    {
        // 验证明文哈希与验证
        string password = "MySecurePassword_2026!";
        string hash = PasswordHasherService.HashPassword(password);

        Assert.StartsWith("$argon2", hash);
        Assert.True(PasswordHasherService.VerifyPassword(password, hash));
        Assert.False(PasswordHasherService.VerifyPassword("WrongPassword", hash));
    }

    [Fact]
    public void TestJwtTokenLifecycle()
    {
        var settings = new OrdoSettings
        {
            AppSecretKey = "test-secret-key-that-is-long-enough-for-hs256-signature-1234567890",
            AccessTokenMinutes = 60
        };
        var jwt = new JwtTokenService(settings);

        string userId = "user-uuid-12345";
        string token = jwt.CreateAccessToken(userId);
        string? extracted = jwt.ValidateAndGetUserId(token);

        Assert.Equal(userId, extracted);

        // 验证应用访问 Token
        string appToken = jwt.CreateAppAccessToken("workflow-id-1", "grant-id-2");
        var appAuth = jwt.ValidateAppAccessToken(appToken);

        Assert.NotNull(appAuth);
        Assert.Equal("workflow-id-1", appAuth.Value.WorkflowId);
        Assert.Equal("grant-id-2", appAuth.Value.GrantId);
    }
}
