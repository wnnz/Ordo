using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Microsoft.EntityFrameworkCore;

namespace Ordo.Backend.Common.Auth;

/// <summary>
/// 请求范围内的当前登录用户上下文。
/// </summary>
public class CurrentUserContext
{
    private readonly IHttpContextAccessor _httpContextAccessor;
    private readonly JwtTokenService _jwt;
    private readonly OrdoDbContext _db;
    private User? _user;

    public CurrentUserContext(IHttpContextAccessor httpContextAccessor, JwtTokenService jwt, OrdoDbContext db)
    {
        _httpContextAccessor = httpContextAccessor;
        _jwt = jwt;
        _db = db;
    }

    /// <summary>
    /// 获取当前登录用户，如果未登录或 Token 无效则返回 null。
    /// </summary>
    public async Task<User?> GetCurrentUserAsync(CancellationToken ct = default)
    {
        if (_user != null) return _user;

        var httpContext = _httpContextAccessor.HttpContext;
        if (httpContext == null) return null;

        if (!httpContext.Request.Headers.TryGetValue("Authorization", out var authHeader))
        {
            return null;
        }

        string authStr = authHeader.ToString();
        if (!authStr.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        string token = authStr["Bearer ".Length..].Trim();
        string? userId = _jwt.ValidateAndGetUserId(token);
        if (string.IsNullOrEmpty(userId)) return null;

        _user = await _db.Users.FirstOrDefaultAsync(u => u.Id == userId && u.IsActive, ct);
        return _user;
    }

    /// <summary>
    /// 获取当前用户，若未登录直接抛出 401 Unauthorized。
    /// </summary>
    public async Task<User> RequireUserAsync(CancellationToken ct = default)
    {
        var user = await GetCurrentUserAsync(ct);
        if (user == null)
        {
            throw new BadHttpRequestException("Unauthorized", StatusCodes.Status401Unauthorized);
        }
        return user;
    }
}
