using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Common.Auth;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;
using Ordo.Backend.DTOs;

namespace Ordo.Backend.Controllers;

[ApiController]
[Route("api/v1/admin/settings")]
[Route("api/v1/system-settings")]
public class SystemSettingsController : ControllerBase
{
    private record SettingSpec(string Key, object Default, long? Minimum, long? Maximum, string Unit, string Type);

    private readonly OrdoDbContext _db;
    private readonly CurrentUserContext _currentUser;
    private readonly OrdoSettings _settings;

    public SystemSettingsController(OrdoDbContext db, CurrentUserContext currentUser, OrdoSettings settings)
    {
        _db = db;
        _currentUser = currentUser;
        _settings = settings;
    }

    private List<SettingSpec> GetSpecs() => new()
    {
        new("max_upload_bytes", _settings.MaxUploadBytes, 1024, 1024L * 1024L * 1024L, "bytes", "integer"),
        new("public_rate_limit_requests", _settings.PublicRateLimitRequests, 0, 100_000, "requests", "integer"),
        new("public_access_rate_limit_requests", _settings.PublicAccessRateLimitRequests, 0, 100_000, "requests", "integer"),
        new("public_upload_rate_limit_requests", _settings.PublicUploadRateLimitRequests, 0, 100_000, "requests", "integer"),
        new("public_rate_limit_window_seconds", _settings.PublicRateLimitWindowSeconds, 1, 86_400, "seconds", "integer"),
        new("public_max_active_runs_per_app", _settings.PublicMaxActiveRunsPerApp, 1, 10_000, "runs", "integer"),
        new("workflow_run_lease_seconds", _settings.WorkflowRunLeaseSeconds, 30, 86_400, "seconds", "integer"),
        new("workflow_pending_recovery_seconds", _settings.WorkflowPendingRecoverySeconds, 30, 86_400, "seconds", "integer"),
        new("file_upload_retention_hours", _settings.FileUploadRetentionHours, 1, 8_760, "hours", "integer"),
        new("file_output_retention_days", _settings.FileOutputRetentionDays, 1, 3_650, "days", "integer"),
        new("file_orphan_grace_hours", _settings.FileOrphanGraceHours, 1, 8_760, "hours", "integer"),
        new("file_cleanup_batch_size", _settings.FileCleanupBatchSize, 1, 10_000, "files", "integer"),
        new("disable_user_registration", _settings.DisableUserRegistration, null, null, "", "boolean")
    };

    [HttpGet]
    public async Task<ActionResult<List<SystemSettingOut>>> GetSettings(CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        if (!user.IsPlatformAdmin)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { error = "Admin required" });
        }

        var dbRows = await _db.SystemSettings.ToDictionaryAsync(s => s.Key, s => s, ct);
        var specs = GetSpecs();
        var result = new List<SystemSettingOut>();

        foreach (var spec in specs)
        {
            bool hasDbRow = dbRows.TryGetValue(spec.Key, out var row);
            object val = spec.Default;

            if (hasDbRow && row != null)
            {
                try
                {
                    if (spec.Type == "boolean")
                    {
                        val = JsonSerializer.Deserialize<bool>(row.Value);
                    }
                    else
                    {
                        val = JsonSerializer.Deserialize<long>(row.Value);
                    }
                }
                catch
                {
                    val = spec.Default;
                }
            }

            result.Add(new SystemSettingOut
            {
                Key = spec.Key,
                Value = val,
                Default = spec.Default,
                Minimum = spec.Minimum,
                Maximum = spec.Maximum,
                Unit = spec.Unit,
                Type = spec.Type,
                Source = hasDbRow ? "database" : "environment",
                UpdatedAt = hasDbRow ? row?.UpdatedAt : null
            });
        }

        return Ok(result);
    }

    [HttpPut]
    [HttpPatch]
    public async Task<ActionResult<List<SystemSettingOut>>> UpdateSettings([FromBody] SystemSettingsUpdateRequest request, CancellationToken ct)
    {
        var user = await _currentUser.RequireUserAsync(ct);
        if (!user.IsPlatformAdmin)
        {
            return StatusCode(StatusCodes.Status403Forbidden, new { error = "Admin required" });
        }

        var specs = GetSpecs().ToDictionary(s => s.Key);

        foreach (var (key, rawVal) in request.Values)
        {
            if (!specs.TryGetValue(key, out var spec)) continue;

            object normalizedVal = rawVal switch
            {
                JsonElement elem => elem.ValueKind switch
                {
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Number => elem.GetInt64(),
                    _ => spec.Default
                },
                bool b => b,
                int i => (long)i,
                long l => l,
                double d => (long)d,
                _ => spec.Default
            };

            // 如果设置值等于默认值，从数据库删除以回退到环境配置
            bool isDefault = Equals(normalizedVal, spec.Default);
            var existing = await _db.SystemSettings.FirstOrDefaultAsync(s => s.Key == key, ct);

            if (isDefault)
            {
                if (existing != null)
                {
                    _db.SystemSettings.Remove(existing);
                }
            }
            else
            {
                string jsonVal = JsonSerializer.Serialize(normalizedVal);
                if (existing != null)
                {
                    existing.Value = jsonVal;
                    existing.UpdatedBy = user.Id;
                    existing.UpdatedAt = DateTime.UtcNow;
                }
                else
                {
                    _db.SystemSettings.Add(new SystemSetting
                    {
                        Key = key,
                        Value = jsonVal,
                        UpdatedBy = user.Id,
                        UpdatedAt = DateTime.UtcNow
                    });
                }
            }
        }

        await _db.SaveChangesAsync(ct);
        return await GetSettings(ct);
    }
}
