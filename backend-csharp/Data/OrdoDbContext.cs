using Microsoft.EntityFrameworkCore;
using Ordo.Backend.Data.Entities;

namespace Ordo.Backend.Data;

/// <summary>
/// Ordo 主数据库上下文，管理与 PostgreSQL 的交互。
/// </summary>
public class OrdoDbContext : DbContext
{
    public OrdoDbContext(DbContextOptions<OrdoDbContext> options) : base(options)
    {
    }

    public DbSet<User> Users => Set<User>();
    public DbSet<SystemSetting> SystemSettings => Set<SystemSetting>();
    public DbSet<Workspace> Workspaces => Set<Workspace>();
    public DbSet<WorkspaceMember> WorkspaceMembers => Set<WorkspaceMember>();
    public DbSet<WorkspaceInvitation> WorkspaceInvitations => Set<WorkspaceInvitation>();
    public DbSet<AuditEvent> AuditEvents => Set<AuditEvent>();
    public DbSet<Script> Scripts => Set<Script>();
    public DbSet<ScriptVersion> ScriptVersions => Set<ScriptVersion>();
    public DbSet<WorkflowFolder> WorkflowFolders => Set<WorkflowFolder>();
    public DbSet<Workflow> Workflows => Set<Workflow>();
    public DbSet<WorkflowEnvironmentVariable> WorkflowEnvironmentVariables => Set<WorkflowEnvironmentVariable>();
    public DbSet<WorkflowAccessGrant> WorkflowAccessGrants => Set<WorkflowAccessGrant>();
    public DbSet<WorkflowVersion> WorkflowVersions => Set<WorkflowVersion>();
    public DbSet<WorkflowRun> WorkflowRuns => Set<WorkflowRun>();
    public DbSet<WorkflowApproval> WorkflowApprovals => Set<WorkflowApproval>();
    public DbSet<ApiKey> ApiKeys => Set<ApiKey>();
    public DbSet<ModelProvider> ModelProviders => Set<ModelProvider>();
    public DbSet<StoredFile> StoredFiles => Set<StoredFile>();
    public DbSet<Dataset> Datasets => Set<Dataset>();
    public DbSet<KnowledgeDocument> KnowledgeDocuments => Set<KnowledgeDocument>();
    public DbSet<KnowledgeChunk> KnowledgeChunks => Set<KnowledgeChunk>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // 唯一索引与组合索引匹配
        modelBuilder.Entity<User>(entity =>
        {
            entity.HasIndex(e => e.Email).IsUnique();
        });

        modelBuilder.Entity<Workspace>(entity =>
        {
            entity.HasIndex(e => e.Slug).IsUnique();
        });

        modelBuilder.Entity<WorkspaceMember>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.UserId }).IsUnique();
        });

        modelBuilder.Entity<WorkspaceInvitation>(entity =>
        {
            entity.HasIndex(e => e.TokenHash).IsUnique();
        });

        modelBuilder.Entity<Script>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.Slug }).IsUnique();
        });

        modelBuilder.Entity<ScriptVersion>(entity =>
        {
            entity.HasIndex(e => new { e.ScriptId, e.Version }).IsUnique();
        });

        modelBuilder.Entity<WorkflowFolder>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.Name }).IsUnique();
        });

        modelBuilder.Entity<Workflow>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.Slug }).IsUnique();
            entity.HasIndex(e => e.Slug).HasDatabaseName("ux_workflows_slug").IsUnique();
        });

        modelBuilder.Entity<WorkflowEnvironmentVariable>(entity =>
        {
            entity.HasIndex(e => new { e.WorkflowId, e.Name }).IsUnique();
        });

        modelBuilder.Entity<WorkflowVersion>(entity =>
        {
            entity.HasIndex(e => new { e.WorkflowId, e.Version }).IsUnique();
        });

        modelBuilder.Entity<WorkflowRun>(entity =>
        {
            entity.HasIndex(e => new { e.WorkflowId, e.TriggeredBy, e.IdempotencyKey })
                .HasDatabaseName("ux_workflow_runs_idempotency")
                .IsUnique();
        });

        modelBuilder.Entity<ApiKey>(entity =>
        {
            entity.HasIndex(e => e.KeyHash).IsUnique();
        });

        modelBuilder.Entity<ModelProvider>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.Name }).IsUnique();
        });

        modelBuilder.Entity<StoredFile>(entity =>
        {
            entity.HasIndex(e => e.ObjectKey).IsUnique();
        });

        modelBuilder.Entity<Dataset>(entity =>
        {
            entity.HasIndex(e => new { e.WorkspaceId, e.Name }).IsUnique();
        });
    }
}
