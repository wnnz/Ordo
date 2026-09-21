using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Data;
using Ordo.Backend.DTOs;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/admin")]
public class AdminController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;

    public AdminController(OrdoDbContext db, CurrentUserContext currentUser)
    {
        _db = db;
        _currentUser = currentUser;
    }

    [HttpGet("users")]
    public async Task<ActionResult<List<UserResponse>>> ListUsers(CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        if (!user.IsPlatformAdmin)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { error = "Admin required" });
        }

        var users = await _db.Users
            .OrderBy(u => u.CreatedAt)
            .Select(u => new UserResponse
            {
                Id = u.Id,
                Email = u.Email,
                DisplayName = u.DisplayName,
                IsActive = u.IsActive,
                IsPlatformAdmin = u.IsPlatformAdmin,
                CreatedAt = u.CreatedAt
            })
            .ToListAsync(ct);

        return Ok(users);
    }
}
