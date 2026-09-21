using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/auth")]
public class AuthController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly JwtTokenService _jwt;
    private readonly CurrentUserContext _currentUser;
    private readonly OrdoSettings _settings;

    public AuthController(OrdoDbContext db, JwtTokenService jwt, CurrentUserContext currentUser, OrdoSettings settings)
    {
        _db = db;
        _jwt = jwt;
        _currentUser = currentUser;
        _settings = settings;
    }

    [HttpPost("register")]
    public async Task<ActionResult<TokenResponse>> Register([FromBody] RegisterRequest request, CancellationToken ct)
    {
        string email = request.Email.Trim().ToLowerInvariant();

        if (await _db.Users.AnyAsync(u => u.Email == email, ct))
        {
            return Conflict(new { error = "Email already registered" });
        }

        int userCount = await _db.Users.CountAsync(ct);
        if (userCount > 0 && _settings.DisableUserRegistration)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { error = "User registration is disabled" });
        }

        bool isFirstUser = userCount == 0;
        var user = new User
        {
            Email = email,
            DisplayName = request.DisplayName.Trim(),
            PasswordHash = PasswordHasherService.HashPassword(request.Password),
            IsPlatformAdmin = isFirstUser,
            IsActive = true
        };

        _db.Users.Add(user);
        await _db.SaveChangesAsync(ct);

        // 为新用户创建默认个人工作区
        string slug = GenerateSlug(user.DisplayName);
        var workspace = new Workspace
        {
            Name = $"{user.DisplayName}'s Workspace",
            Slug = slug
        };
        _db.Workspaces.Add(workspace);
        await _db.SaveChangesAsync(ct);

        var member = new WorkspaceMember
        {
            WorkspaceId = workspace.Id,
            UserId = user.Id,
            Role = "owner"
        };
        _db.WorkspaceMembers.Add(member);
        await _db.SaveChangesAsync(ct);

        string token = _jwt.CreateAccessToken(user.Id);
        return StatusCode(StatusCodes.Status201Created, new TokenResponse
        {
            AccessToken = token,
            User = MapUser(user)
        });
    }

    [HttpPost("login")]
    public async Task<ActionResult<TokenResponse>> Login([FromBody] LoginRequest request, CancellationToken ct)
    {
        string email = request.Email.Trim().ToLowerInvariant();
        var user = await _db.Users.FirstOrDefaultAsync(u => u.Email == email, ct);

        if (user == null || !PasswordHasherService.VerifyPassword(request.Password, user.PasswordHash))
        {
            return Unauthorized(new { error = "Invalid email or password" });
        }

        if (!user.IsActive)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { error = "User account is disabled" });
        }

        string token = _jwt.CreateAccessToken(user.Id);
        return Ok(new TokenResponse
        {
            AccessToken = token,
            User = MapUser(user)
        });
    }

    [HttpGet("me")]
    public async Task<ActionResult<UserResponse>> GetMe(CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        return Ok(MapUser(user));
    }

    [HttpGet("registration-status")]
    public async Task<ActionResult<object>> GetRegistrationStatus(CancellationToken ct)
    {
        int count = await _db.Users.CountAsync(ct);
        bool disabled = count > 0 && _settings.DisableUserRegistration;
        return Ok(new { enabled = !disabled });
    }

    private static UserResponse MapUser(User user) => new()
    {
        Id = user.Id,
        Email = user.Email,
        DisplayName = user.DisplayName,
        IsActive = user.IsActive,
        IsPlatformAdmin = user.IsPlatformAdmin,
        CreatedAt = user.CreatedAt
    };

    private static string GenerateSlug(string name)
    {
        string raw = name.ToLowerInvariant().Replace(' ', '-');
        string clean = new string(raw.Where(c => char.IsLetterOrDigit(c) || c == '-').ToArray());
        return string.IsNullOrWhiteSpace(clean) ? Guid.NewGuid().ToString("N")[..8] : clean;
    }
}
