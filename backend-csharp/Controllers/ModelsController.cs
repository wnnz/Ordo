using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/workspaces/{workspaceId}/models")]
public class ModelsController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;
    private readonly WorkspaceAuthorizationService _authorization;
    private readonly CredentialEncryptionService _encryption;

    /// <summary>
    /// 初始化模型供应商控制器。
    /// </summary>
    public ModelsController(
        OrdoDbContext db,
        CurrentUserContext currentUser,
        WorkspaceAuthorizationService authorization,
        CredentialEncryptionService encryption)
    {
        _db = db;
        _currentUser = currentUser;
        _authorization = authorization;
        _encryption = encryption;
    }

    [HttpGet]
    public async Task<ActionResult<List<ModelProviderResponse>>> ListProviders(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var list = await _db.ModelProviders
            .Where(m => m.WorkspaceId == workspaceId)
            .OrderBy(m => m.CreatedAt)
            .Select(m => new ModelProviderResponse
            {
                Id = m.Id,
                WorkspaceId = m.WorkspaceId,
                Name = m.Name,
                ProviderType = m.ProviderType,
                BaseUrl = m.BaseUrl,
                DefaultModel = m.DefaultModel,
                Config = ParseJson(m.Config),
                CreatedAt = m.CreatedAt
            })
            .ToListAsync(ct);

        return Ok(list);
    }

    [HttpPost]
    public async Task<ActionResult<ModelProviderResponse>> CreateProvider(string workspaceId, [FromBody] ModelProviderCreateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "admin", ct);

        var provider = new ModelProvider
        {
            WorkspaceId = workspaceId,
            Name = request.Name.Trim(),
            ProviderType = request.ProviderType,
            BaseUrl = request.BaseUrl.Trim(),
            EncryptedApiKey = _encryption.Encrypt(request.ApiKey),
            DefaultModel = request.DefaultModel.Trim(),
            Config = request.Config != null ? JsonSerializer.Serialize(request.Config) : "{}",
            CreatedBy = user.Id
        };

        _db.ModelProviders.Add(provider);
        await _db.SaveChangesAsync(ct);

        return StatusCode(StatusCodes.Status201Created, new ModelProviderResponse
        {
            Id = provider.Id,
            WorkspaceId = provider.WorkspaceId,
            Name = provider.Name,
            ProviderType = provider.ProviderType,
            BaseUrl = provider.BaseUrl,
            DefaultModel = provider.DefaultModel,
            Config = ParseJson(provider.Config),
            CreatedAt = provider.CreatedAt
        });
    }

    [HttpDelete("{providerId}")]
    public async Task<ActionResult<object>> DeleteProvider(string workspaceId, string providerId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "admin", ct);

        var provider = await _db.ModelProviders
            .FirstOrDefaultAsync(m => m.WorkspaceId == workspaceId && m.Id == providerId, ct);

        if (provider == null) return NotFound();

        _db.ModelProviders.Remove(provider);
        await _db.SaveChangesAsync(ct);

        return Ok(new { message = "Model provider deleted" });
    }

    private static object ParseJson(string json)
    {
        if (string.IsNullOrWhiteSpace(json)) return new Dictionary<string, object>();
        try
        {
            return JsonSerializer.Deserialize<JsonElement>(json);
        }
        catch
        {
            return json;
        }
    }
}
