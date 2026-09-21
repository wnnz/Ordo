using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.IdentityModel.Tokens;
using Ordo.Backend.Common.Configuration;

namespace Ordo.Backend.Common.Security;

/// <summary>
/// 负责系统 JWT Access Token 与公开应用 Access Token 的生成与解析。
/// </summary>
public class JwtTokenService
{
    private readonly OrdoSettings _settings;
    private readonly SymmetricSecurityKey _securityKey;

    public JwtTokenService(OrdoSettings settings)
    {
        _settings = settings;
        _securityKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_settings.AppSecretKey));
    }

    /// <summary>
    /// 为已登录用户创建标准后台访问令牌。
    /// </summary>
    public string CreateAccessToken(string userId)
    {
        var tokenHandler = new JwtSecurityTokenHandler();
        var tokenDescriptor = new SecurityTokenDescriptor
        {
            Subject = new ClaimsIdentity(new[]
            {
                new Claim(JwtRegisteredClaimNames.Sub, userId)
            }),
            Expires = DateTime.UtcNow.AddMinutes(_settings.AccessTokenMinutes),
            SigningCredentials = new SigningCredentials(_securityKey, SecurityAlgorithms.HmacSha256)
        };

        var token = tokenHandler.CreateToken(tokenDescriptor);
        return tokenHandler.WriteToken(token);
    }

    /// <summary>
    /// 解析用户 Token 并提取用户 ID。
    /// </summary>
    public string? ValidateAndGetUserId(string token)
    {
        var tokenHandler = new JwtSecurityTokenHandler();
        var validationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = _securityKey,
            ValidateIssuer = false,
            ValidateAudience = false,
            ClockSkew = TimeSpan.Zero
        };

        try
        {
            var principal = tokenHandler.ValidateToken(token, validationParameters, out _);
            return principal.FindFirst(ClaimTypes.NameIdentifier)?.Value
                   ?? principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// 为公开应用创建受保护的访问凭据。
    /// </summary>
    public string CreateAppAccessToken(string workflowId, string grantId, DateTime? expiresAt = null)
    {
        var tokenHandler = new JwtSecurityTokenHandler();
        var exp = DateTime.UtcNow.AddHours(12);
        if (expiresAt.HasValue && expiresAt.Value < exp)
        {
            exp = expiresAt.Value;
        }

        var tokenDescriptor = new SecurityTokenDescriptor
        {
            Subject = new ClaimsIdentity(new[]
            {
                new Claim(JwtRegisteredClaimNames.Sub, workflowId),
                new Claim("grant_id", grantId),
                new Claim("kind", "app_access")
            }),
            Expires = exp,
            SigningCredentials = new SigningCredentials(_securityKey, SecurityAlgorithms.HmacSha256)
        };

        var token = tokenHandler.CreateToken(tokenDescriptor);
        return tokenHandler.WriteToken(token);
    }

    /// <summary>
    /// 校验公开应用 Token 并返回 (workflowId, grantId)。
    /// </summary>
    public (string WorkflowId, string GrantId)? ValidateAppAccessToken(string token)
    {
        var tokenHandler = new JwtSecurityTokenHandler();
        var validationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = _securityKey,
            ValidateIssuer = false,
            ValidateAudience = false,
            ClockSkew = TimeSpan.Zero
        };

        try
        {
            var principal = tokenHandler.ValidateToken(token, validationParameters, out _);
            string? kind = principal.FindFirst("kind")?.Value;
            if (kind != "app_access") return null;

            string? sub = principal.FindFirst(ClaimTypes.NameIdentifier)?.Value
                          ?? principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value;
            string? grantId = principal.FindFirst("grant_id")?.Value;

            if (string.IsNullOrEmpty(sub) || string.IsNullOrEmpty(grantId)) return null;

            return (sub, grantId);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// 计算 SHA-256 十六进制哈希（用于 API Key、邀请 Token 比对）。
    /// </summary>
    public static string ComputeSha256Hex(string input)
    {
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
