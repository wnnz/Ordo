using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Data;
using Ordo.Backend.Data.Entities;

namespace Ordo.Backend.Common.Auth;

/// <summary>
/// 集中执行工作区成员关系、角色等级和资源归属校验，避免各控制器出现跨租户访问漏洞。
/// </summary>
public sealed class WorkspaceAuthorizationService
{
    /// <summary>
    /// 工作区角色从低到高的固定等级。
    /// </summary>
    private static readonly IReadOnlyDictionary<string, int> RoleRanks = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
    {
        ["viewer"] = 0,
        ["editor"] = 1,
        ["admin"] = 2,
        ["owner"] = 3
    };

    /// <summary>
    /// 数据库上下文。
    /// </summary>
    private readonly OrdoDbContext _db;

    /// <summary>
    /// 初始化工作区授权服务。
    /// </summary>
    /// <param name="db">当前请求的数据库上下文。</param>
    public WorkspaceAuthorizationService(OrdoDbContext db)
    {
        _db = db;
    }

    /// <summary>
    /// 验证用户是工作区成员且角色不低于指定等级。
    /// </summary>
    /// <param name="workspaceId">目标工作区 ID。</param>
    /// <param name="userId">当前用户 ID。</param>
    /// <param name="minimumRole">允许操作的最低角色。</param>
    /// <param name="ct">请求取消令牌。</param>
    /// <returns>已验证的工作区成员关系。</returns>
    /// <exception cref="BadHttpRequestException">用户不是成员、角色不足或角色配置无效时抛出。</exception>
    public async Task<WorkspaceMember> RequireRoleAsync(
        string workspaceId,
        string userId,
        string minimumRole,
        CancellationToken ct = default)
    {
        if (!RoleRanks.TryGetValue(minimumRole, out int minimumRank))
        {
            throw new InvalidOperationException($"Unknown workspace role: {minimumRole}");
        }

        var member = await _db.WorkspaceMembers
            .AsNoTracking()
            .FirstOrDefaultAsync(item => item.WorkspaceId == workspaceId && item.UserId == userId, ct);

        if (member == null)
        {
            throw new BadHttpRequestException("Not a member of this workspace", StatusCodes.Status403Forbidden);
        }

        if (!RoleRanks.TryGetValue(member.Role, out int memberRank) || memberRank < minimumRank)
        {
            throw new BadHttpRequestException("Insufficient workspace privileges", StatusCodes.Status403Forbidden);
        }

        return member;
    }

    /// <summary>
    /// 验证可选工作流 ID 属于指定工作区，防止创建跨工作区绑定关系。
    /// </summary>
    /// <param name="workspaceId">目标工作区 ID。</param>
    /// <param name="workflowId">可选工作流 ID。</param>
    /// <param name="ct">请求取消令牌。</param>
    /// <exception cref="BadHttpRequestException">工作流不存在于目标工作区时抛出。</exception>
    public async Task RequireWorkflowAsync(string workspaceId, string? workflowId, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(workflowId))
        {
            return;
        }

        bool exists = await _db.Workflows.AnyAsync(
            item => item.Id == workflowId && item.WorkspaceId == workspaceId && item.DeletedAt == null,
            ct);
        if (!exists)
        {
            throw new BadHttpRequestException("Workflow not found in this workspace", StatusCodes.Status404NotFound);
        }
    }
}
