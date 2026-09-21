using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Background;
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

    public PublicAppsController(
        OrdoDbContext db,
        WorkflowQueue queue,
        RunEventsService eventsService,
        JwtTokenService jwt)
    {
        _db = db;
        _queue = queue;
        _eventsService = eventsService;
        _jwt = jwt;
    }

    [HttpGet("{appSlug}")]
    public async Task<ActionResult<PublicAppMetaResponse>> GetAppMeta(string appSlug, CancellationToken ct)
    {
        var (workflow, version) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null || version == null) return NotFound();

        var inputFields = new List<object>();
        try
        {
            using var doc = JsonDocument.Parse(version.Graph);
            if (doc.RootElement.TryGetProperty("nodes", out var nodes))
            {
                foreach (var n in nodes.EnumerateArray())
                {
                    if (n.TryGetProperty("type", out var t) && t.GetString() == "start" &&
                        n.TryGetProperty("data", out var data) &&
                        data.TryGetProperty("inputs", out var inps))
                    {
                        inputFields.AddRange(inps.EnumerateArray().Select(x => (object)x));
                    }
                }
            }
        }
        catch { }

        return Ok(new PublicAppMetaResponse
        {
            Id = workflow.Id,
            Name = workflow.Name,
            Slug = workflow.Slug,
            Description = workflow.Description,
            AppType = workflow.AppType,
            PublishedAccess = workflow.PublishedAccess,
            InputFields = inputFields
        });
    }

    [HttpPost("{appSlug}/access")]
    public async Task<ActionResult<AppAccessResponse>> RequestAccess(string appSlug, [FromBody] AppAccessRequest request, CancellationToken ct)
    {
        var (workflow, _) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null) return NotFound();

        // 查找密码授权
        var grant = await _db.WorkflowAccessGrants
            .FirstOrDefaultAsync(g => g.WorkflowId == workflow.Id && g.GrantType == "password", ct);

        if (grant == null || string.IsNullOrEmpty(grant.PasswordHash) || !PasswordHasherService.VerifyPassword(request.Password, grant.PasswordHash))
        {
            return Unauthorized(new { error = "Invalid access password" });
        }

        string token = _jwt.CreateAppAccessToken(workflow.Id, grant.Id, grant.ExpiresAt);
        return Ok(new AppAccessResponse { AppToken = token });
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
        var (workflow, _) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null) return NotFound();

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkflowId == workflow.Id && r.Id == runId, ct);

        if (run == null) return NotFound();
        return Ok(MapRun(run));
    }

    [HttpGet("{appSlug}/runs/{runId}/events")]
    public async Task GetPublicRunEvents(string appSlug, string runId, CancellationToken ct)
    {
        var (workflow, _) = await GetPublishedAsync(appSlug, ct);
        if (workflow == null)
        {
            Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkflowId == workflow.Id && r.Id == runId, ct);

        if (run == null)
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

        // 校验受保护公开访问
        if (workflow.PublishedAccess == "protected")
        {
            if (!Request.Headers.TryGetValue("Authorization", out var authHeader) || string.IsNullOrEmpty(authHeader))
            {
                return Unauthorized(new { error = "Authorization required" });
            }

            string raw = authHeader.ToString().Replace("Bearer ", "", StringComparison.OrdinalIgnoreCase).Trim();
            // 检查是 AppToken 还是 API Key
            var appAuth = _jwt.ValidateAppAccessToken(raw);
            if (appAuth == null || appAuth.Value.WorkflowId != workflow.Id)
            {
                // 检查 API Key
                string hash = JwtTokenService.ComputeSha256Hex(raw);
                bool keyValid = await _db.ApiKeys.AnyAsync(k => k.WorkspaceId == workflow.WorkspaceId && k.KeyHash == hash && k.RevokedAt == null, ct);
                if (!keyValid)
                {
                    return Unauthorized(new { error = "Invalid token or API key" });
                }
            }
        }

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
