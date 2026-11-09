using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/workspaces/{workspaceId}/scripts")]
public class ScriptsController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;
    private readonly WorkspaceAuthorizationService _authorization;

    /// <summary>
    /// 初始化脚本控制器。
    /// </summary>
    public ScriptsController(
        OrdoDbContext db,
        CurrentUserContext currentUser,
        WorkspaceAuthorizationService authorization)
    {
        _db = db;
        _currentUser = currentUser;
        _authorization = authorization;
    }

    [HttpGet]
    public async Task<ActionResult<List<object>>> ListScripts(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var list = await _db.Scripts
            .Where(s => s.WorkspaceId == workspaceId && s.DeletedAt == null)
            .OrderByDescending(s => s.UpdatedAt)
            .Select(s => new
            {
                id = s.Id,
                name = s.Name,
                slug = s.Slug,
                description = s.Description,
                latest_version = s.LatestVersion,
                created_at = s.CreatedAt,
                updated_at = s.UpdatedAt
            })
            .ToListAsync(ct);

        return Ok(list);
    }

    public class CreateScriptRequest
    {
        public string Name { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public string SourceCode { get; set; } = "def main(inputs):\n    return {'result': 'ok'}\n";
    }

    [HttpPost]
    public async Task<ActionResult<object>> CreateScript(string workspaceId, [FromBody] CreateScriptRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var script = new Script
        {
            WorkspaceId = workspaceId,
            Name = request.Name.Trim(),
            Slug = request.Name.ToLowerInvariant().Replace(' ', '-'),
            Description = request.Description,
            LatestVersion = 1,
            CreatedBy = user.Id
        };
        _db.Scripts.Add(script);
        await _db.SaveChangesAsync(ct);

        string hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(request.SourceCode))).ToLowerInvariant();
        var version = new ScriptVersion
        {
            WorkspaceId = workspaceId,
            ScriptId = script.Id,
            Version = 1,
            SourceType = "python",
            SourceCode = request.SourceCode,
            Entrypoint = "main",
            ContentHash = hash,
            CreatedBy = user.Id
        };
        _db.ScriptVersions.Add(version);
        await _db.SaveChangesAsync(ct);

        return StatusCode(StatusCodes.Status201Created, new
        {
            id = script.Id,
            name = script.Name,
            slug = script.Slug,
            latest_version = 1
        });
    }

    [HttpDelete("{scriptId}")]
    public async Task<ActionResult<object>> DeleteScript(string workspaceId, string scriptId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var s = await _db.Scripts
            .FirstOrDefaultAsync(item => item.WorkspaceId == workspaceId && item.Id == scriptId && item.DeletedAt == null, ct);

        if (s == null) return NotFound();

        s.DeletedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(new { message = "Script deleted" });
    }
}
