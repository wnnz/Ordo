using System.Security.Cryptography;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/workspaces/{workspaceId}/api-keys")]
public class ApiKeysController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;
    private readonly WorkspaceAuthorizationService _authorization;

    /// <summary>
    /// 初始化 API Key 控制器。
    /// </summary>
    public ApiKeysController(
        OrdoDbContext db,
        CurrentUserContext currentUser,
        WorkspaceAuthorizationService authorization)
    {
        _db = db;
        _currentUser = currentUser;
        _authorization = authorization;
    }

    [HttpGet]
    public async Task<ActionResult<List<object>>> ListKeys(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "admin", ct);

        var keys = await _db.ApiKeys
            .Where(k => k.WorkspaceId == workspaceId && k.RevokedAt == null)
            .OrderByDescending(k => k.CreatedAt)
            .Select(k => new
            {
                id = k.Id,
                name = k.Name,
                key_prefix = k.KeyPrefix,
                workflow_id = k.WorkflowId,
                last_used_at = k.LastUsedAt,
                created_at = k.CreatedAt
            })
            .ToListAsync(ct);

        return Ok(keys);
    }

    public class CreateApiKeyRequest
    {
        public string Name { get; set; } = string.Empty;
        public string? WorkflowId { get; set; }
    }

    [HttpPost]
    public async Task<ActionResult<object>> CreateKey(string workspaceId, [FromBody] CreateApiKeyRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "admin", ct);
        await _authorization.RequireWorkflowAsync(workspaceId, request.WorkflowId, ct);

        string rawKey = $"owf_{Convert.ToBase64String(RandomNumberGenerator.GetBytes(24)).Replace('+', '-').Replace('/', '_').TrimEnd('=')}";
        string prefix = rawKey[..Math.Min(12, rawKey.Length)];
        string hash = JwtTokenService.ComputeSha256Hex(rawKey);

        var apiKey = new ApiKey
        {
            WorkspaceId = workspaceId,
            WorkflowId = request.WorkflowId,
            Name = request.Name.Trim(),
            KeyPrefix = prefix,
            KeyHash = hash,
            CreatedBy = user.Id
        };

        _db.ApiKeys.Add(apiKey);
        await _db.SaveChangesAsync(ct);

        return StatusCode(StatusCodes.Status201Created, new
        {
            id = apiKey.Id,
            name = apiKey.Name,
            token = rawKey, // 明文仅在创建时返回一次
            key_prefix = prefix,
            created_at = apiKey.CreatedAt
        });
    }

    [HttpDelete("{keyId}")]
    public async Task<ActionResult<object>> RevokeKey(string workspaceId, string keyId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "admin", ct);

        var apiKey = await _db.ApiKeys
            .FirstOrDefaultAsync(k => k.WorkspaceId == workspaceId && k.Id == keyId && k.RevokedAt == null, ct);

        if (apiKey == null) return NotFound();

        apiKey.RevokedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(new { message = "API key revoked" });
    }
}
