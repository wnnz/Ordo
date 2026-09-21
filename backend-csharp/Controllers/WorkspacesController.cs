using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/workspaces")]
public class WorkspacesController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;

    public WorkspacesController(OrdoDbContext db, CurrentUserContext currentUser)
    {
        _db = db;
        _currentUser = currentUser;
    }

    [HttpGet]
    public async Task<ActionResult<List<WorkspaceResponse>>> ListWorkspaces(CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);

        var query = from m in _db.WorkspaceMembers
                    join w in _db.Workspaces on m.WorkspaceId equals w.Id
                    where m.UserId == user.Id && w.DeletedAt == null
                    orderby w.CreatedAt
                    select new WorkspaceResponse
                    {
                        Id = w.Id,
                        Name = w.Name,
                        Slug = w.Slug,
                        Description = w.Description,
                        Icon = w.Icon,
                        Timezone = w.Timezone,
                        IsArchived = w.IsArchived,
                        Role = m.Role,
                        Version = w.Version,
                        CreatedAt = w.CreatedAt
                    };

        var list = await query.ToListAsync(ct);
        return Ok(list);
    }

    [HttpPost]
    public async Task<ActionResult<WorkspaceResponse>> CreateWorkspace([FromBody] WorkspaceCreateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);

        string slug = GenerateSlug(request.Name);
        var workspace = new Workspace
        {
            Name = request.Name.Trim(),
            Slug = slug,
            Description = request.Description,
            Timezone = request.Timezone
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

        return StatusCode(StatusCodes.Status201Created, new WorkspaceResponse
        {
            Id = workspace.Id,
            Name = workspace.Name,
            Slug = workspace.Slug,
            Description = workspace.Description,
            Timezone = workspace.Timezone,
            IsArchived = workspace.IsArchived,
            Role = "owner",
            Version = workspace.Version,
            CreatedAt = workspace.CreatedAt
        });
    }

    [HttpPatch("{workspaceId}")]
    public async Task<ActionResult<WorkspaceResponse>> UpdateWorkspace(string workspaceId, [FromBody] WorkspaceUpdateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await RequireRoleAsync(workspaceId, user.Id, "admin", ct);

        var ws = await _db.Workspaces.FirstOrDefaultAsync(w => w.Id == workspaceId && w.DeletedAt == null, ct);
        if (ws == null) return NotFound();

        if (ws.Version != request.Version)
        {
            return Conflict(new { error = "Workspace was updated by another member" });
        }

        if (request.Name != null) ws.Name = request.Name.Trim();
        if (request.Description != null) ws.Description = request.Description;
        if (request.Icon != null) ws.Icon = request.Icon;
        if (request.Timezone != null) ws.Timezone = request.Timezone;

        ws.Version++;
        await _db.SaveChangesAsync(ct);

        return Ok(new WorkspaceResponse
        {
            Id = ws.Id,
            Name = ws.Name,
            Slug = ws.Slug,
            Description = ws.Description,
            Icon = ws.Icon,
            Timezone = ws.Timezone,
            IsArchived = ws.IsArchived,
            Role = "admin",
            Version = ws.Version,
            CreatedAt = ws.CreatedAt
        });
    }

    [HttpPost("{workspaceId}/archive")]
    public async Task<ActionResult<WorkspaceResponse>> ArchiveWorkspace(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await RequireRoleAsync(workspaceId, user.Id, "owner", ct);

        var ws = await _db.Workspaces.FirstOrDefaultAsync(w => w.Id == workspaceId && w.DeletedAt == null, ct);
        if (ws == null) return NotFound();

        ws.IsArchived = true;
        await _db.SaveChangesAsync(ct);

        return Ok(new WorkspaceResponse
        {
            Id = ws.Id,
            Name = ws.Name,
            Slug = ws.Slug,
            Description = ws.Description,
            IsArchived = true,
            Role = "owner",
            Version = ws.Version,
            CreatedAt = ws.CreatedAt
        });
    }

    [HttpPost("{workspaceId}/restore")]
    public async Task<ActionResult<WorkspaceResponse>> RestoreWorkspace(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await RequireRoleAsync(workspaceId, user.Id, "owner", ct);

        var ws = await _db.Workspaces.FirstOrDefaultAsync(w => w.Id == workspaceId && w.DeletedAt == null, ct);
        if (ws == null) return NotFound();

        ws.IsArchived = false;
        await _db.SaveChangesAsync(ct);

        return Ok(new WorkspaceResponse
        {
            Id = ws.Id,
            Name = ws.Name,
            Slug = ws.Slug,
            Description = ws.Description,
            IsArchived = false,
            Role = "owner",
            Version = ws.Version,
            CreatedAt = ws.CreatedAt
        });
    }

    [HttpDelete("{workspaceId}")]
    public async Task<ActionResult<object>> DeleteWorkspace(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await RequireRoleAsync(workspaceId, user.Id, "owner", ct);

        var ws = await _db.Workspaces.FirstOrDefaultAsync(w => w.Id == workspaceId && w.DeletedAt == null, ct);
        if (ws == null) return NotFound();

        ws.DeletedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(new { message = "Workspace scheduled for deletion" });
    }

    [HttpGet("{workspaceId}/members")]
    public async Task<ActionResult<List<WorkspaceMemberResponse>>> ListMembers(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var members = await _db.WorkspaceMembers
            .Include(m => m.User)
            .Where(m => m.WorkspaceId == workspaceId)
            .OrderBy(m => m.JoinedAt)
            .Select(m => new WorkspaceMemberResponse
            {
                Id = m.Id,
                WorkspaceId = m.WorkspaceId,
                UserId = m.UserId,
                Role = m.Role,
                JoinedAt = m.JoinedAt,
                User = m.User != null ? new UserResponse
                {
                    Id = m.User.Id,
                    Email = m.User.Email,
                    DisplayName = m.User.DisplayName,
                    IsActive = m.User.IsActive,
                    IsPlatformAdmin = m.User.IsPlatformAdmin,
                    CreatedAt = m.User.CreatedAt
                } : null
            })
            .ToListAsync(ct);

        return Ok(members);
    }

    private async Task RequireRoleAsync(string workspaceId, string userId, string minRole, CancellationToken ct)
    {
        var member = await _db.WorkspaceMembers
            .FirstOrDefaultAsync(m => m.WorkspaceId == workspaceId && m.UserId == userId, ct);

        if (member == null)
        {
            throw new BadHttpRequestException("Forbidden: Not a member of this workspace", StatusCodes.Status403Forbidden);
        }

        var rolesOrder = new List<string> { "viewer", "editor", "admin", "owner" };
        int userIdx = rolesOrder.IndexOf(member.Role.ToLowerInvariant());
        int reqIdx = rolesOrder.IndexOf(minRole.ToLowerInvariant());

        if (userIdx < reqIdx)
        {
            throw new BadHttpRequestException("Forbidden: Insufficient privileges", StatusCodes.Status403Forbidden);
        }
    }

    private static string GenerateSlug(string name)
    {
        string raw = name.ToLowerInvariant().Replace(' ', '-');
        string clean = new string(raw.Where(c => char.IsLetterOrDigit(c) || c == '-').ToArray());
        return string.IsNullOrWhiteSpace(clean) ? Guid.NewGuid().ToString("N")[..8] : clean;
    }
}
