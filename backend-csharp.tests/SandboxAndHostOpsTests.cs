using Docker.DotNet;
using Microsoft.Extensions.Logging.Abstractions;
using Ordo.Backend.Common.Configuration;
using Ordo.Backend.HostOps;
using Ordo.Backend.Sandbox;

namespace backend_csharp.tests;

/// <summary>
/// 宿主机操作与进程内 Docker 沙箱的集成测试。
/// 需要 Windows 宿主机 + Docker Desktop（npipe）+ ordo-sandbox 镜像；不满足时直接跳过。
/// </summary>
public class SandboxAndHostOpsTests
{
    private static async Task<bool> DockerAvailableAsync()
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }
        try
        {
            using var client = new DockerClientConfiguration(new Uri("npipe://./pipe/docker_engine")).CreateClient();
            await client.System.PingAsync();
            var image = await client.Images.InspectImageAsync("ordo-sandbox");
            return image != null;
        }
        catch
        {
            return false;
        }
    }

    [Fact]
    public void HostInfoCollector_ReturnsAdapters()
    {
        if (!OperatingSystem.IsWindows()) return;

        var info = HostInfoCollector.Collect();

        Assert.NotNull(info);
        Assert.NotEmpty(info.Adapters);
    }

    [Fact]
    public async Task Sandbox_ExecutesSimpleScript()
    {
        if (!await DockerAvailableAsync()) return;

        var settings = new OrdoSettings { StoragePath = Path.GetTempPath() };
        var service = new SandboxExecutionService(settings, NullLogger<SandboxExecutionService>.Instance);

        var result = await service.ExecuteAsync(new SandboxExecuteRequest
        {
            Source = "def main(inputs, context):\n    return {'result': inputs['value'] * 2}\n",
            Inputs = new Dictionary<string, object?> { ["value"] = 21 },
        }, CancellationToken.None);

        Assert.Equal("succeeded", result["status"]?.ToString());
        var outputs = Assert.IsType<Dictionary<string, object?>>(result["outputs"]);
        Assert.Equal(42L, Convert.ToInt64(outputs["result"]));
    }

    [Fact]
    public async Task Sandbox_ReportsScriptFailure()
    {
        if (!await DockerAvailableAsync()) return;

        var settings = new OrdoSettings { StoragePath = Path.GetTempPath() };
        var service = new SandboxExecutionService(settings, NullLogger<SandboxExecutionService>.Instance);

        var result = await service.ExecuteAsync(new SandboxExecuteRequest
        {
            Source = "def main(inputs, context):\n    raise RuntimeError('boom')\n",
            Inputs = new Dictionary<string, object?>(),
        }, CancellationToken.None);

        Assert.Equal("failed", result["status"]?.ToString());
        Assert.Contains("boom", result["error"]?.ToString());
    }

    [Fact]
    public async Task Sandbox_CollectsOutputFileArtifact()
    {
        if (!await DockerAvailableAsync()) return;

        string artifactDir = Path.Combine(Path.GetTempPath(), $"ordo-artifacts-{Guid.NewGuid():N}");
        var settings = new OrdoSettings
        {
            StoragePath = Path.GetTempPath(),
            SandboxArtifactPath = artifactDir,
        };
        var service = new SandboxExecutionService(settings, NullLogger<SandboxExecutionService>.Instance);

        const string source = """
import os

def main(inputs, context):
    path = os.path.join(context['output_dir'], 'hello.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('sandbox-output')
    return {'file': context['output_file'](path)}
""";

        var result = await service.ExecuteAsync(new SandboxExecuteRequest { Source = source }, CancellationToken.None);

        Assert.Equal("succeeded", result["status"]?.ToString());
        var outputs = Assert.IsType<Dictionary<string, object?>>(result["outputs"]);
        var file = Assert.IsType<Dictionary<string, object?>>(outputs["file"]);
        Assert.Equal("hello.txt", file["filename"]?.ToString());
        var artifactRef = Assert.IsType<string>(file["__ordo_artifact_path"]);
        string artifactPath = Path.Combine(artifactDir, artifactRef.Replace('/', Path.DirectorySeparatorChar));
        Assert.True(File.Exists(artifactPath));
        Assert.Equal("sandbox-output", await File.ReadAllTextAsync(artifactPath));

        Directory.Delete(artifactDir, recursive: true);
    }
}
