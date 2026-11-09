using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Background;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;
using Ordo.Backend.Services;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/workspaces/{workspaceId}/workflows")]
public class WorkflowsController : ControllerBase
{
    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;
    private readonly WorkspaceAuthorizationService _authorization;
    private readonly WorkflowQueue _queue;
    private readonly RunEventsService _eventsService;

    /// <summary>
    /// 初始化工作流控制器。
    /// </summary>
    public WorkflowsController(
        OrdoDbContext db,
        CurrentUserContext currentUser,
        WorkspaceAuthorizationService authorization,
        WorkflowQueue queue,
        RunEventsService eventsService)
    {
        _db = db;
        _currentUser = currentUser;
        _authorization = authorization;
        _queue = queue;
        _eventsService = eventsService;
    }

    [HttpGet]
    public async Task<ActionResult<List<WorkflowResponse>>> ListWorkflows(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var list = await _db.Workflows
            .Where(w => w.WorkspaceId == workspaceId && w.DeletedAt == null)
            .OrderByDescending(w => w.UpdatedAt)
            .Select(w => MapWorkflow(w))
            .ToListAsync(ct);

        return Ok(list);
    }

    [HttpPost]
    public async Task<ActionResult<WorkflowResponse>> CreateWorkflow(string workspaceId, [FromBody] WorkflowCreateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        string defaultGraph = "{\"schema_version\":1,\"nodes\":[{\"id\":\"start\",\"type\":\"start\",\"position\":{\"x\":80,\"y\":160},\"data\":{\"label\":\"Start\"}},{\"id\":\"end\",\"type\":\"end\",\"position\":{\"x\":480,\"y\":160},\"data\":{\"label\":\"End\"}}],\"edges\":[{\"id\":\"e1\",\"source\":\"start\",\"target\":\"end\"}]}";

        var workflow = new Workflow
        {
            WorkspaceId = workspaceId,
            FolderId = request.FolderId,
            Name = request.Name.Trim(),
            Slug = GenerateSlug(request.Name),
            Description = request.Description,
            AppType = request.AppType,
            DraftGraph = defaultGraph,
            DraftVersion = 1,
            PublishedAccess = "public",
            CreatedBy = user.Id
        };

        _db.Workflows.Add(workflow);
        await _db.SaveChangesAsync(ct);

        return StatusCode(StatusCodes.Status201Created, MapWorkflow(workflow));
    }

    [HttpGet("{workflowId}")]
    public async Task<ActionResult<WorkflowResponse>> GetWorkflow(string workspaceId, string workflowId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var wf = await _db.Workflows
            .FirstOrDefaultAsync(w => w.WorkspaceId == workspaceId && w.Id == workflowId && w.DeletedAt == null, ct);

        if (wf == null) return NotFound();
        return Ok(MapWorkflow(wf));
    }

    [HttpPut("{workflowId}")]
    [HttpPatch("{workflowId}")]
    public async Task<ActionResult<WorkflowResponse>> UpdateWorkflow(string workspaceId, string workflowId, [FromBody] WorkflowUpdateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var wf = await _db.Workflows
            .FirstOrDefaultAsync(w => w.WorkspaceId == workspaceId && w.Id == workflowId && w.DeletedAt == null, ct);

        if (wf == null) return NotFound(new { detail = "Workflow not found" });

        if (request.ExpectedVersion.HasValue && wf.DraftVersion != request.ExpectedVersion.Value)
        {
            return Conflict(new { detail = "Workflow was updated by another member" });
        }

        if (request.Name != null) wf.Name = request.Name.Trim();
        if (request.Description != null) wf.Description = request.Description;
        if (request.FolderId != null) wf.FolderId = request.FolderId;
        if (request.PublishedAccess != null) wf.PublishedAccess = request.PublishedAccess;

        if (request.Slug != null && !string.Equals(request.Slug, wf.Slug, StringComparison.Ordinal))
        {
            string normalizedSlug = request.Slug.Trim();
            bool duplicateSlug = await _db.Workflows.AnyAsync(
                item => item.Id != workflowId && item.Slug == normalizedSlug && item.DeletedAt == null,
                ct);
            if (duplicateSlug)
            {
                return Conflict(new { detail = "Workflow slug already exists" });
            }
            wf.Slug = normalizedSlug;
        }

        object? graph = request.Graph ?? request.DraftGraph;
        if (graph != null)
        {
            wf.DraftGraph = graph is string s ? s : JsonSerializer.Serialize(graph);
            wf.DraftVersion++;
        }

        wf.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(MapWorkflow(wf));
    }

    [HttpPost("{workflowId}/publish")]
    public async Task<ActionResult<WorkflowResponse>> PublishWorkflow(string workspaceId, string workflowId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var wf = await _db.Workflows
            .FirstOrDefaultAsync(w => w.WorkspaceId == workspaceId && w.Id == workflowId && w.DeletedAt == null, ct);

        if (wf == null) return NotFound();

        int latestVersion = await _db.WorkflowVersions
            .Where(v => v.WorkflowId == workflowId)
            .MaxAsync(v => (int?)v.Version, ct) ?? 0;

        var version = new WorkflowVersion
        {
            WorkspaceId = workspaceId,
            WorkflowId = wf.Id,
            Version = latestVersion + 1,
            Graph = wf.DraftGraph,
            CreatedBy = user.Id
        };

        _db.WorkflowVersions.Add(version);
        await _db.SaveChangesAsync(ct);

        wf.PublishedVersionId = version.Id;
        wf.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(MapWorkflow(wf));
    }

    [HttpPost("{workflowId}/run")]
    public async Task<ActionResult<RunResponse>> TriggerRun(string workspaceId, string workflowId, [FromBody] RunCreateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var wf = await _db.Workflows
            .FirstOrDefaultAsync(w => w.WorkspaceId == workspaceId && w.Id == workflowId && w.DeletedAt == null, ct);

        if (wf == null) return NotFound();

        string graph = wf.DraftGraph;
        string? versionId = null;

        if (!request.RunAsDraft && !string.IsNullOrEmpty(wf.PublishedVersionId))
        {
            versionId = wf.PublishedVersionId;
            var pv = await _db.WorkflowVersions.FirstOrDefaultAsync(v => v.Id == versionId, ct);
            if (pv != null) graph = pv.Graph;
        }

        var run = new WorkflowRun
        {
            WorkspaceId = workspaceId,
            WorkflowId = wf.Id,
            WorkflowVersionId = versionId,
            Status = "pending",
            TriggeredBy = "studio",
            TriggerUserId = user.Id,
            Inputs = JsonSerializer.Serialize(request.Inputs),
            ExecutionGraph = graph,
            CreatedBy = user.Id
        };

        _db.WorkflowRuns.Add(run);
        await _db.SaveChangesAsync(ct);

        // 投递到 Channel 队列供后台消费
        await _queue.EnqueueAsync(run.Id, null, ct);

        return StatusCode(StatusCodes.Status201Created, MapRun(run));
    }

    [HttpGet("{workflowId}/runs")]
    public async Task<ActionResult<RunPageResponse>> ListRuns(
        string workspaceId,
        string workflowId,
        [FromQuery] int limit = 50,
        [FromQuery] int offset = 0,
        CancellationToken ct = default)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        limit = Math.Clamp(limit, 1, 100);
        offset = Math.Max(offset, 0);
        var query = _db.WorkflowRuns
            .Where(r => r.WorkspaceId == workspaceId && r.WorkflowId == workflowId);
        int total = await query.CountAsync(ct);
        var runs = await query
            .OrderByDescending(r => r.CreatedAt)
            .Skip(offset)
            .Take(limit)
            .Select(r => MapRun(r))
            .ToListAsync(ct);

        return Ok(new RunPageResponse
        {
            Items = runs,
            Total = total,
            Limit = limit,
            Offset = offset
        });
    }

    [HttpGet("{workflowId}/runs/{runId}")]
    public async Task<ActionResult<RunResponse>> GetRun(string workspaceId, string workflowId, string runId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkspaceId == workspaceId && r.WorkflowId == workflowId && r.Id == runId, ct);

        if (run == null) return NotFound();
        return Ok(MapRun(run));
    }

    [HttpGet("{workflowId}/runs/{runId}/events")]
    public async Task GetRunEvents(string workspaceId, string workflowId, string runId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var run = await _db.WorkflowRuns
            .FirstOrDefaultAsync(r => r.WorkspaceId == workspaceId && r.WorkflowId == workflowId && r.Id == runId, ct);

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

    [HttpGet("folders")]
    public async Task<ActionResult<List<WorkflowFolderResponse>>> ListFolders(string workspaceId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "viewer", ct);

        var folders = await _db.WorkflowFolders
            .Where(f => f.WorkspaceId == workspaceId)
            .OrderBy(f => f.Name)
            .ToListAsync(ct);

        var counts = await _db.Workflows
            .Where(w => w.WorkspaceId == workspaceId && w.FolderId != null && w.DeletedAt == null)
            .GroupBy(w => w.FolderId!)
            .Select(g => new { FolderId = g.Key, Count = g.Count() })
            .ToDictionaryAsync(x => x.FolderId, x => x.Count, ct);

        var result = folders.Select(f => new WorkflowFolderResponse
        {
            Id = f.Id,
            WorkspaceId = f.WorkspaceId,
            Name = f.Name,
            WorkflowCount = counts.TryGetValue(f.Id, out int count) ? count : 0,
            CreatedAt = f.CreatedAt,
            UpdatedAt = f.UpdatedAt
        }).ToList();

        return Ok(result);
    }

    [HttpPost("folders")]
    public async Task<ActionResult<WorkflowFolderResponse>> CreateFolder(string workspaceId, [FromBody] WorkflowFolderCreateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        bool duplicate = await _db.WorkflowFolders.AnyAsync(f => f.WorkspaceId == workspaceId && f.Name == request.Name.Trim(), ct);
        if (duplicate)
        {
            return Conflict(new { error = "Workflow folder name already exists" });
        }

        var folder = new WorkflowFolder
        {
            WorkspaceId = workspaceId,
            Name = request.Name.Trim(),
            CreatedBy = user.Id
        };

        _db.WorkflowFolders.Add(folder);
        await _db.SaveChangesAsync(ct);

        return StatusCode(StatusCodes.Status201Created, new WorkflowFolderResponse
        {
            Id = folder.Id,
            WorkspaceId = folder.WorkspaceId,
            Name = folder.Name,
            WorkflowCount = 0,
            CreatedAt = folder.CreatedAt,
            UpdatedAt = folder.UpdatedAt
        });
    }

    [HttpPatch("folders/{folderId}")]
    public async Task<ActionResult<WorkflowFolderResponse>> UpdateFolder(string workspaceId, string folderId, [FromBody] WorkflowFolderUpdateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var folder = await _db.WorkflowFolders.FirstOrDefaultAsync(f => f.WorkspaceId == workspaceId && f.Id == folderId, ct);
        if (folder == null) return NotFound();

        bool duplicate = await _db.WorkflowFolders.AnyAsync(f => f.WorkspaceId == workspaceId && f.Name == request.Name.Trim() && f.Id != folderId, ct);
        if (duplicate)
        {
            return Conflict(new { error = "Workflow folder name already exists" });
        }

        folder.Name = request.Name.Trim();
        folder.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        int count = await _db.Workflows.CountAsync(w => w.WorkspaceId == workspaceId && w.FolderId == folderId && w.DeletedAt == null, ct);

        return Ok(new WorkflowFolderResponse
        {
            Id = folder.Id,
            WorkspaceId = folder.WorkspaceId,
            Name = folder.Name,
            WorkflowCount = count,
            CreatedAt = folder.CreatedAt,
            UpdatedAt = folder.UpdatedAt
        });
    }

    [HttpDelete("folders/{folderId}")]
    public async Task<IActionResult> DeleteFolder(string workspaceId, string folderId, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var folder = await _db.WorkflowFolders.FirstOrDefaultAsync(f => f.WorkspaceId == workspaceId && f.Id == folderId, ct);
        if (folder == null) return NotFound();

        int count = await _db.Workflows.CountAsync(w => w.WorkspaceId == workspaceId && w.FolderId == folderId && w.DeletedAt == null, ct);
        if (count > 0)
        {
            return Conflict(new { error = "Workflow folder must be empty before deletion" });
        }

        _db.WorkflowFolders.Remove(folder);
        await _db.SaveChangesAsync(ct);

        return NoContent();
    }

    [HttpPatch("{workflowId}/folder")]
    public async Task<ActionResult<WorkflowResponse>> MoveWorkflowFolder(string workspaceId, string workflowId, [FromBody] WorkflowFolderMoveRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        await _authorization.RequireRoleAsync(workspaceId, user.Id, "editor", ct);

        var wf = await _db.Workflows.FirstOrDefaultAsync(w => w.WorkspaceId == workspaceId && w.Id == workflowId && w.DeletedAt == null, ct);
        if (wf == null) return NotFound();

        if (!string.IsNullOrEmpty(request.FolderId))
        {
            bool folderExists = await _db.WorkflowFolders.AnyAsync(f => f.WorkspaceId == workspaceId && f.Id == request.FolderId, ct);
            if (!folderExists) return NotFound(new { error = "Folder not found" });
        }

        wf.FolderId = request.FolderId;
        wf.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync(ct);

        return Ok(MapWorkflow(wf));
    }

    private static WorkflowResponse MapWorkflow(Workflow w) => new()
    {
        Id = w.Id,
        WorkspaceId = w.WorkspaceId,
        FolderId = w.FolderId,
        Name = w.Name,
        Slug = w.Slug,
        Description = w.Description,
        AppType = w.AppType,
        DraftGraph = ParseJson(w.DraftGraph),
        DraftVersion = w.DraftVersion,
        PublishedVersionId = w.PublishedVersionId,
        PublishedAccess = w.PublishedAccess,
        NextRunAt = w.NextRunAt,
        CreatedBy = w.CreatedBy,
        CreatedAt = w.CreatedAt,
        UpdatedAt = w.UpdatedAt
    };

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

    private static string GenerateSlug(string name)
    {
        string raw = name.ToLowerInvariant().Replace(' ', '-');
        string clean = new string(raw.Where(c => char.IsLetterOrDigit(c) || c == '-').ToArray());
        return string.IsNullOrWhiteSpace(clean) ? Guid.NewGuid().ToString("N")[..8] : clean;
    }
}
