using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Background;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Security;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;
using Ordo.Backend.Services;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("v1/apps")]
public class PublicAppsController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly WorkflowQueue _queue;
    private readonly RunEventsService _eventsService;
    private readonly JwtTokenService _jwt;
    private readonly CurrentUserContext _currentUser;

    /// <summary>
    /// 初始化公开应用控制器。
    /// </summary>
    public PublicAppsController(
        OrdoDbContext db,
        WorkflowQueue queue,
        RunEventsService eventsService,
        JwtTokenService jwt,
        CurrentUserContext currentUser)
    {
        _db = db;
        _queue = queue;
        _eventsService = eventsService;
        _jwt = jwt;
        _currentUser = currentUser;
    }

    [HttpGet("{appSlug}")]
    public async Task<ActionResult<PublicAppMetaResponse>> GetAppMeta(string appSlug, CancellationToken ct)
    {
        var (workflow, version) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null || version == null) return NotFound();

        var inputFields = new List<object>();
        var triggers = new List<string> { "api" };
        try
        {
            using var doc = JsonDocument.Parse(version.Graph);
            if (doc.RootElement.TryGetProperty("nodes", out var nodes))
            {
                foreach (var node in nodes.EnumerateArray())
                {
                    if (!node.TryGetProperty("type", out var type) || type.GetString() != "start" ||
                        !node.TryGetProperty("data", out var data))
                    {
                        continue;
                    }

                    JsonElement config = data.TryGetProperty("config", out var nestedConfig) ? nestedConfig : data;
                    if (config.TryGetProperty("input_fields", out var fields) && fields.ValueKind == JsonValueKind.Array)
                    {
                        inputFields.AddRange(fields.EnumerateArray().Select(item => (object)item.Clone()));
                    }
                    if (config.TryGetProperty("triggers", out var configuredTriggers) && configuredTriggers.ValueKind == JsonValueKind.Array)
                    {
                        triggers = configuredTriggers.EnumerateArray()
                            .Select(item => item.GetString())
                            .Where(item => !string.IsNullOrWhiteSpace(item))
                            .Select(item => item!)
                            .ToList();
                    }
                    break;
                }
            }
        }
        catch (JsonException)
        {
            // 已发布图损坏时保持最小元数据响应，由运行入口返回具体错误。
        }

        DateTime now = DateTime.UtcNow;
        var grantTypes = workflow.PublishedAccess == "protected"
            ? await _db.WorkflowAccessGrants
                .Where(grant => grant.WorkflowId == workflow.Id && (!grant.ExpiresAt.HasValue || grant.ExpiresAt > now))
                .Select(grant => grant.GrantType)
                .ToListAsync(ct)
            : new List<string>();

        return Ok(new PublicAppMetaResponse
        {
            Id = workflow.Id,
            Name = workflow.Name,
            Slug = workflow.Slug,
            Description = workflow.Description,
            AppType = workflow.AppType,
            PublishedAccess = workflow.PublishedAccess,
            Access = workflow.PublishedAccess,
            AccessOptions = new Dictionary<string, bool>
            {
                ["login"] = grantTypes.Any(type => type is "all_users" or "user"),
                ["password"] = grantTypes.Contains("password")
            },
            Version = version.Version,
            Triggers = triggers,
            InputFields = inputFields
        });
    }

    [HttpPost("{appSlug}/access")]
    public async Task<ActionResult<AppAccessResponse>> RequestAccess(string appSlug, [FromBody] AppAccessRequest request, CancellationToken ct)
    {
        var (workflow, _) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null) return NotFound(new { detail = "Published app not found" });
        if (workflow.PublishedAccess != "protected")
        {
            return Ok(new AppAccessResponse());
        }

        if (Request.Headers.TryGetValue("X-App-Access", out var storedToken) && !string.IsNullOrWhiteSpace(storedToken))
        {
            var storedGrant = await ValidatePasswordGrantAsync(workflow, storedToken.ToString(), ct);
            if (storedGrant == null)
            {
                return Unauthorized(new { detail = "Invalid app access token" });
            }
            return Ok(new AppAccessResponse
            {
                AccessToken = storedToken.ToString(),
                AppToken = storedToken.ToString(),
                GrantId = storedGrant.Id
            });
        }

        if (!string.IsNullOrWhiteSpace(request.Password))
        {
            DateTime now = DateTime.UtcNow;
            var passwordGrants = await _db.WorkflowAccessGrants
                .Where(grant => grant.WorkflowId == workflow.Id && grant.GrantType == "password" &&
                    (!grant.ExpiresAt.HasValue || grant.ExpiresAt > now))
                .ToListAsync(ct);
            var grant = passwordGrants.FirstOrDefault(item =>
                !string.IsNullOrEmpty(item.PasswordHash) &&
                PasswordHasherService.VerifyPassword(request.Password, item.PasswordHash));
            if (grant == null)
            {
                return Unauthorized(new { detail = "Invalid or expired access password" });
            }

            string token = _jwt.CreateAppAccessToken(workflow.Id, grant.Id, grant.ExpiresAt);
            return Ok(new AppAccessResponse
            {
                AccessToken = token,
                AppToken = token,
                GrantId = grant.Id
            });
        }

        var user = await _currentUser.GetCurrentUserAsync(ct);
        if (user == null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }
        bool allowed = await HasUserGrantAsync(workflow.Id, user.Id, ct);
        if (!allowed)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { detail = "User does not have access to this app" });
        }
        return Ok(new AppAccessResponse { UserId = user.Id });
    }

    [HttpPost("{appSlug}/form")]
    public async Task<ActionResult<RunResponse>> SubmitForm(string appSlug, [FromBody] RunCreateRequest request, CancellationToken ct)
    {
        return await ExecutePublicRunAsync(appSlug, request, "form", ct);
    }

    [HttpPost("{appSlug}/run")]
    public async Task<ActionResult<RunResponse>> ExecuteRunApi(string appSlug, [FromBody] RunCreateRequest request, CancellationToken ct)
    {
        return await ExecutePublicRunAsync(appSlug, request, "api", ct);
    }

    [HttpPost("{appSlug}/webhook")]
    public async Task<ActionResult<RunResponse>> ExecuteWebhook(string appSlug, [FromBody] RunCreateRequest request, CancellationToken ct)
    {
        return await ExecutePublicRunAsync(appSlug, request, "webhook", ct);
    }

    [HttpGet("{appSlug}/runs/{runId}")]
    public async Task<ActionResult<RunResponse>> GetPublicRun(string appSlug, string runId, CancellationToken ct)
    {
        var (workflow, version) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null || version == null) return NotFound(new { detail = "Published app not found" });
        var credential = await AuthorizePublicAsync(workflow, ct);
        if (credential == null) return Unauthorized(new { detail = "Authentication or app access required" });

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkflowId == workflow.Id && r.WorkflowVersionId == version.Id && r.Id == runId, ct);

        if (run == null || !CanReadRun(credential, run)) return NotFound(new { detail = "Workflow run not found" });
        return Ok(MapRun(run));
    }

    [HttpGet("{appSlug}/runs/{runId}/events")]
    public async Task GetPublicRunEvents(string appSlug, string runId, CancellationToken ct)
    {
        var (workflow, version) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null || version == null)
        {
            Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }
        var credential = await AuthorizePublicAsync(workflow, ct);
        if (credential == null)
        {
            Response.StatusCode = StatusCodes.Status401Unauthorized;
            return;
        }

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkflowId == workflow.Id && r.WorkflowVersionId == version.Id && r.Id == runId, ct);

        if (run == null || !CanReadRun(credential, run))
        {
            Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        Response.ContentType = "text/event-stream";
        Response.Headers.CacheControl = "no-cache";
        Response.Headers.Append("X-Accel-Buffering", "no");

        await foreach (var sseChunk in _eventsService.StreamRunEventsAsync(run.Id, run.Status, ct))
        {
            await Response.WriteAsync(sseChunk, ct);
            await Response.Body.FlushAsync(ct);
        }
    }

    private async Task<ActionResult<RunResponse>> ExecutePublicRunAsync(string appSlug, RunCreateRequest request, string triggerType, CancellationToken ct)
    {
        var (workflow, version) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null || version == null) return NotFound();

        var credential = await AuthorizePublicAsync(workflow, ct);
        if (credential == null)
        {
            return Unauthorized(new { detail = "Authentication or app access required" });
        }
        if (triggerType is "api" or "webhook" && workflow.PublishedAccess == "protected" && credential.Value.Kind != "api_key")
        {
            return Unauthorized(new { detail = "Workflow API key required" });
        }

        string? triggerUserId = credential.Value.Kind switch
        {
            "user" => credential.Value.Id,
            "grant" => $"grant:{credential.Value.Id}",
            _ => null
        };

        var run = new WorkflowRun
        {
            WorkspaceId = workflow.WorkspaceId,
            WorkflowId = workflow.Id,
            WorkflowVersionId = version.Id,
            Status = "pending",
            TriggeredBy = triggerType,
            Inputs = JsonSerializer.Serialize(request.Inputs),
            ExecutionGraph = version.Graph,
            IdempotencyKey = request.IdempotencyKey
        };

        _db.WorkflowRuns.Add(run);
        await _db.SaveChangesAsync(ct);

        await _queue.EnqueueAsync(run.Id, null, ct);

        return StatusCode(StatusCodes.Status201Created, MapRun(run));
    }

    /// <summary>
    /// 验证当前公开请求使用的密码令牌、API Key 或登录用户授权。
    /// </summary>
    /// <param name="workflow">目标公开工作流。</param>
    /// <param name="ct">请求取消令牌。</param>
    /// <returns>授权类型和授权主体 ID；公开应用返回 public，失败返回 null。</returns>
    private async Task<(string Kind, string? Id)?> AuthorizePublicAsync(Workflow workflow, CancellationToken ct)
    {
        if (workflow.PublishedAccess != "protected")
        {
            return ("public", null);
        }

        if (Request.Headers.TryGetValue("X-App-Access", out var appAccess) && !string.IsNullOrWhiteSpace(appAccess))
        {
            var grant = await ValidatePasswordGrantAsync(workflow, appAccess.ToString(), ct);
            return grant == null ? null : ("grant", grant.Id);
        }

        if (Request.Headers.TryGetValue("Authorization", out var authorization))
        {
            string raw = authorization.ToString();
            if (raw.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
            {
                raw = raw["Bearer ".Length..].Trim();
            }
            if (raw.StartsWith("owf_", StringComparison.Ordinal))
            {
                string hash = JwtTokenService.ComputeSha256Hex(raw);
                var key = await _db.ApiKeys.FirstOrDefaultAsync(item =>
                    item.WorkspaceId == workflow.WorkspaceId &&
                    (item.WorkflowId == null || item.WorkflowId == workflow.Id) &&
                    item.KeyHash == hash && item.RevokedAt == null,
                    ct);
                return key == null ? null : ("api_key", key.Id);
            }
        }

        var user = await _currentUser.GetCurrentUserAsync(ct);
        if (user != null && await HasUserGrantAsync(workflow.Id, user.Id, ct))
        {
            return ("user", user.Id);
        }
        return null;
    }

    /// <summary>
    /// 验证密码授权令牌仍指向当前工作流中有效的密码授权记录。
    /// </summary>
    /// <param name="workflow">目标公开工作流。</param>
    /// <param name="token">X-App-Access 令牌。</param>
    /// <param name="ct">请求取消令牌。</param>
    /// <returns>有效授权记录；无效或过期时返回 null。</returns>
    private async Task<WorkflowAccessGrant?> ValidatePasswordGrantAsync(
        Workflow workflow,
        string token,
        CancellationToken ct)
    {
        var decoded = _jwt.ValidateAppAccessToken(token);
        if (decoded == null || decoded.Value.WorkflowId != workflow.Id)
        {
            return null;
        }

        DateTime now = DateTime.UtcNow;
        return await _db.WorkflowAccessGrants.FirstOrDefaultAsync(grant =>
            grant.Id == decoded.Value.GrantId &&
            grant.WorkflowId == workflow.Id &&
            grant.GrantType == "password" &&
            (!grant.ExpiresAt.HasValue || grant.ExpiresAt > now),
            ct);
    }

    /// <summary>
    /// 判断登录用户是否拥有当前公开工作流的有效用户授权。
    /// </summary>
    /// <param name="workflowId">目标工作流 ID。</param>
    /// <param name="userId">登录用户 ID。</param>
    /// <param name="ct">请求取消令牌。</param>
    /// <returns>存在 all_users 或当前用户专属授权时返回 true。</returns>
    private Task<bool> HasUserGrantAsync(string workflowId, string userId, CancellationToken ct)
    {
        DateTime now = DateTime.UtcNow;
        return _db.WorkflowAccessGrants.AnyAsync(grant =>
            grant.WorkflowId == workflowId &&
            (grant.GrantType == "all_users" || (grant.GrantType == "user" && grant.UserId == userId)) &&
            (!grant.ExpiresAt.HasValue || grant.ExpiresAt > now),
            ct);
    }

    /// <summary>
    /// 验证授权主体只能读取由自身创建的受保护表单运行。
    /// </summary>
    /// <param name="credential">已验证的授权主体。</param>
    /// <param name="run">目标运行记录。</param>
    /// <returns>当前主体是否可以读取该运行。</returns>
    private static bool CanReadRun((string Kind, string? Id)? credential, WorkflowRun run)
    {
        if (credential == null)
        {
            return false;
        }
        return credential.Value.Kind switch
        {
            "user" => run.TriggeredBy == "form" && run.TriggerUserId == credential.Value.Id,
            "grant" => run.TriggeredBy == "form" && run.TriggerUserId == $"grant:{credential.Value.Id}",
            _ => true
        };
    }

    private async Task<(Workflow? Workflow, WorkflowVersion? Version)> GetPublishedAsync(string slug, CancellationToken ct)
    {
        var wf = await _db.Workflows
            .FirstOrDefaultAsync(w => w.Slug == slug && w.PublishedVersionId != null && w.DeletedAt == null, ct);

        if (wf == null) return (null, null);

        var v = await _db.WorkflowVersions
            .FirstOrDefaultAsync(item => item.Id == wf.PublishedVersionId, ct);

        return (wf, v);
    }

    private static RunResponse MapRun(WorkflowRun r) => new()
    {
        Id = r.Id,
        WorkspaceId = r.WorkspaceId,
        WorkflowId = r.WorkflowId,
        WorkflowVersionId = r.WorkflowVersionId,
        Status = r.Status,
        TriggeredBy = r.TriggeredBy,
        Inputs = ParseJson(r.Inputs),
        Outputs = ParseJson(r.Outputs),
        Trace = ParseJson(r.Trace),
        Error = r.Error,
        StartedAt = r.StartedAt,
        FinishedAt = r.FinishedAt,
        CreatedAt = r.CreatedAt
    };

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
