using System.Diagnostics;
using System.Formats.Tar;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Docker.DotNet;
using Docker.DotNet.Models;
using Ordo.Backend.Common.Configuration;

namespace Ordo.Backend.Sandbox;

/// <summary>
/// 进程内 Python 沙箱控制面：通过 Docker API 创建一次性受限容器执行脚本，
/// 完全复刻原 sandbox/app.py 独立服务的隔离与限额语义。
/// </summary>
public class SandboxExecutionService : IDisposable
{
    private const int MaxSourceBytes = 5_000_000;
    private const int MaxSourceFiles = 100;
    private const int MaxInputBytes = 5_000_000;
    private const int MaxLogBytes = 256_000;
    private const int MaxOutputBytes = 2_000_000;
    private const int MaxInputFiles = 100;
    private const int MaxInputFileBytes = 50 * 1024 * 1024;
    private const int MaxInputFileBytesTotal = 100 * 1024 * 1024;
    private const int MaxOutputFiles = 100;
    private const int MaxOutputFileBytes = 50 * 1024 * 1024;

    private const string InputFileKey = "__ordo_object_key";
    private const string OutputFileKey = "__ordo_output_file";
    private const string ArtifactPathKey = "__ordo_artifact_path";

    private static readonly Regex EntrypointPattern = new(
        @"^(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:)?[A-Za-z_]\w*$", RegexOptions.Compiled);

    private readonly OrdoSettings _settings;
    private readonly ILogger<SandboxExecutionService> _logger;
    private readonly Lazy<IDockerClient> _docker;

    public SandboxExecutionService(OrdoSettings settings, ILogger<SandboxExecutionService> logger)
    {
        _settings = settings;
        _logger = logger;
        _docker = new Lazy<IDockerClient>(() =>
            new DockerClientConfiguration(new Uri(_settings.DockerHost)).CreateClient());
    }

    public void Dispose()
    {
        if (_docker.IsValueCreated)
        {
            _docker.Value.Dispose();
        }
    }

    /// <summary>
    /// 执行脚本并返回与原 sandbox /execute 端点一致的响应字典：
    /// { status, outputs, error, elapsed_ms, logs }。
    /// </summary>
    public async Task<Dictionary<string, object?>> ExecuteAsync(SandboxExecuteRequest payload, CancellationToken ct)
    {
        string jobId = string.IsNullOrEmpty(payload.JobId)
            ? Convert.ToHexString(RandomNumberGenerator.GetBytes(12)).ToLowerInvariant()
            : payload.JobId;
        var started = Stopwatch.GetTimestamp();
        var logs = new List<string>();
        Dictionary<string, object?>? result = null;
        string? containerId = null;
        bool timedOut = false;

        payload.TimeoutSeconds = Math.Clamp(payload.TimeoutSeconds, 1, 300);
        payload.MemoryMb = Math.Clamp(payload.MemoryMb, 64, 2048);

        try
        {
            ValidatePayload(payload);

            Dictionary<string, object?> preparedInputs;
            Dictionary<string, byte[]> inputFiles;
            try
            {
                (preparedInputs, inputFiles) = StageInputFiles(payload.Inputs);
            }
            catch (Exception exc)
            {
                return BuildResult(result = new Dictionary<string, object?>
                {
                    ["status"] = "failed",
                    ["outputs"] = new Dictionary<string, object?>(),
                    ["error"] = exc.Message,
                    ["elapsed_ms"] = ElapsedMs(started),
                }, logs);
            }

            var files = new Dictionary<string, byte[]>();
            foreach (var item in NormalizedFiles(payload.Source, payload.SourceFiles))
            {
                files[item.Key] = Encoding.UTF8.GetBytes(item.Value);
            }
            foreach (var item in inputFiles)
            {
                files[item.Key] = item.Value;
            }
            files["input.json"] = JsonSerializer.SerializeToUtf8Bytes(preparedInputs);
            files["runner.py"] = Encoding.UTF8.GetBytes(RunnerSource(payload));

            await using var archive = new MemoryStream();
            await BuildArchiveAsync(files, archive);
            archive.Position = 0;

            var client = _docker.Value;
            var createResponse = await client.Containers.CreateContainerAsync(new CreateContainerParameters
            {
                Image = _settings.SandboxRuntimeImage,
                Cmd = new List<string> { _settings.SandboxPythonPath, "/workspace/runner.py" },
                NetworkDisabled = !payload.NetworkEnabled,
                Labels = new Dictionary<string, string> { ["ordo.sandbox-job"] = jobId },
                HostConfig = new HostConfig
                {
                    Memory = (long)payload.MemoryMb * 1024 * 1024,
                    NanoCPUs = 500_000_000,
                    PidsLimit = 64,
                    CapDrop = new List<string> { "ALL" },
                    SecurityOpt = new List<string> { "no-new-privileges" },
                    Tmpfs = new Dictionary<string, string> { ["/tmp"] = "rw,noexec,nosuid,size=64m,mode=1777" },
                },
            }, ct);
            containerId = createResponse.ID;

            await client.Containers.ExtractArchiveToContainerAsync(
                containerId, new ContainerPathStatParameters { Path = "/workspace" }, archive, ct);
            await client.Containers.StartContainerAsync(containerId, new ContainerStartParameters(), ct);

            using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(ct);
            using var watchdog = CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token);
            _ = Task.Run(async () =>
            {
                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(payload.TimeoutSeconds), watchdog.Token);
                    timedOut = true;
                    await TryKillAsync(containerId);
                }
                catch (OperationCanceledException) { }
            });

            try
            {
                using var logStream = await client.Containers.GetContainerLogsAsync(
                    containerId,
                    tty: false,
                    new ContainerLogsParameters { ShowStdout = true, ShowStderr = true, Follow = true },
                    cancellation.Token);

                var readBuffer = new byte[64 * 1024];
                var lineBuffer = new List<byte>();
                bool sawResult = false;

                while (true)
                {
                    var read = await logStream.ReadOutputAsync(readBuffer, 0, readBuffer.Length, cancellation.Token);
                    if (read.EOF || read.Count == 0)
                    {
                        break;
                    }

                    for (int i = 0; i < read.Count; i++)
                    {
                        if (readBuffer[i] == (byte)'\n')
                        {
                            string line = Encoding.UTF8.GetString(lineBuffer.ToArray());
                            lineBuffer.Clear();
                            if (await ProcessEventLineAsync(line, containerId, jobId, started, logs, ct) is { } evt)
                            {
                                result = evt;
                                sawResult = true;
                                await TryKillAsync(containerId);
                            }
                            if (sawResult)
                            {
                                break;
                            }
                        }
                        else
                        {
                            lineBuffer.Add(readBuffer[i]);
                        }
                    }
                    if (sawResult)
                    {
                        break;
                    }
                }

                if (!sawResult)
                {
                    var waitResponse = await client.Containers.WaitContainerAsync(containerId, CancellationToken.None);
                    result = new Dictionary<string, object?>
                    {
                        ["status"] = "failed",
                        ["outputs"] = new Dictionary<string, object?>(),
                        ["error"] = timedOut
                            ? "Script execution timed out"
                            : $"Runner exited without a result: {{'StatusCode': {waitResponse.StatusCode}}}",
                        ["elapsed_ms"] = ElapsedMs(started),
                    };
                }
            }
            finally
            {
                await watchdog.CancelAsync();
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            await TryKillAsync(containerId);
            throw;
        }
        catch (Exception exc)
        {
            _logger.LogError(exc, "Sandbox job {JobId} failed before producing a result", jobId);
            result = new Dictionary<string, object?>
            {
                ["status"] = "failed",
                ["outputs"] = new Dictionary<string, object?>(),
                ["error"] = exc.Message,
                ["elapsed_ms"] = ElapsedMs(started),
            };
        }
        finally
        {
            if (containerId != null)
            {
                try
                {
                    await _docker.Value.Containers.RemoveContainerAsync(
                        containerId, new ContainerRemoveParameters { Force = true }, CancellationToken.None);
                }
                catch { }
            }
        }

        return BuildResult(result, logs);
    }

    private static Dictionary<string, object?> BuildResult(Dictionary<string, object?>? result, List<string> logs)
    {
        var response = result ?? new Dictionary<string, object?>
        {
            ["status"] = "failed",
            ["outputs"] = new Dictionary<string, object?>(),
            ["error"] = "Missing result",
            ["elapsed_ms"] = 0L,
        };
        response.Remove("type");
        response["logs"] = logs;
        return response;
    }

    private static long ElapsedMs(long startedTimestamp) =>
        (long)((Stopwatch.GetTimestamp() - startedTimestamp) * 1000.0 / Stopwatch.Frequency);

    private void ValidatePayload(SandboxExecuteRequest payload)
    {
        var files = NormalizedFiles(payload.Source, payload.SourceFiles);
        if (files.Count > MaxSourceFiles)
        {
            throw new InvalidOperationException("Too many script files");
        }
        if (files.Values.Sum(v => Encoding.UTF8.GetByteCount(v)) > MaxSourceBytes)
        {
            throw new InvalidOperationException("Script bundle too large");
        }
        if (JsonSerializer.SerializeToUtf8Bytes(payload.Inputs).Length > MaxInputBytes)
        {
            throw new InvalidOperationException("Script inputs too large");
        }
        if (!EntrypointPattern.IsMatch(payload.Entrypoint))
        {
            throw new InvalidOperationException("Invalid entrypoint");
        }
    }

    /// <summary>
    /// 解析一行 stdout/stderr 为沙箱事件；为 result 事件时返回结果字典。
    /// </summary>
    private async Task<Dictionary<string, object?>?> ProcessEventLineAsync(
        string line, string containerId, string jobId, long started, List<string> logs, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            return null;
        }

        Dictionary<string, JsonElement>? evt;
        try
        {
            evt = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(line);
        }
        catch (JsonException)
        {
            evt = null;
        }

        if (evt == null)
        {
            logs.Add(line.Length > 4000 ? line[..4000] : line);
            return null;
        }

        string? type = evt.TryGetValue("type", out var typeEl) && typeEl.ValueKind == JsonValueKind.String
            ? typeEl.GetString()
            : null;

        if (type == "log")
        {
            logs.Add(evt.TryGetValue("message", out var msg) && msg.ValueKind == JsonValueKind.String
                ? msg.GetString() ?? string.Empty
                : string.Empty);
            return null;
        }

        if (type != "result")
        {
            return null;
        }

        var result = new Dictionary<string, object?>();
        foreach (var pair in evt)
        {
            if (pair.Key == "type")
            {
                continue;
            }
            result[pair.Key] = ToNative(pair.Value);
        }

        string? status = evt.TryGetValue("status", out var statusEl) && statusEl.ValueKind == JsonValueKind.String
            ? statusEl.GetString()
            : null;
        if (status == "succeeded" &&
            evt.TryGetValue("outputs", out var outputsEl) &&
            outputsEl.ValueKind == JsonValueKind.Object)
        {
            var native = ToNative(outputsEl) as Dictionary<string, object?> ?? new Dictionary<string, object?>();
            result["outputs"] = await CollectOutputArtifactsAsync(containerId, native, jobId, ct);
        }

        result["elapsed_ms"] = ElapsedMs(started);
        return result;
    }

    private async Task TryKillAsync(string? containerId)
    {
        if (containerId == null)
        {
            return;
        }
        try
        {
            await _docker.Value.Containers.KillContainerAsync(
                containerId, new ContainerKillParameters(), CancellationToken.None);
        }
        catch { }
    }

    private static Dictionary<string, string> NormalizedFiles(string source, Dictionary<string, string> sourceFiles)
    {
        var rawFiles = sourceFiles is { Count: > 0 } ? sourceFiles : new Dictionary<string, string> { ["main.py"] = source };
        var files = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (rawName, content) in rawFiles)
        {
            string rawPath = (rawName ?? string.Empty).Replace('\\', '/');
            if (!IsValidScriptPath(rawPath))
            {
                throw new InvalidOperationException($"Invalid script path: {rawName}");
            }
            files[rawPath] = content ?? string.Empty;
        }
        return files;
    }

    private static bool IsValidScriptPath(string rawPath)
    {
        if (string.IsNullOrEmpty(rawPath) || rawPath.StartsWith('/') || rawPath.StartsWith("\\\\"))
        {
            return false;
        }
        var parts = rawPath.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0 || parts.Any(p => p is ".." or "."))
        {
            return false;
        }
        if (parts[0].Contains(':'))
        {
            return false;
        }
        return parts[^1].EndsWith(".py", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// 将 inputs 中的 __ordo_object_key 文件引用转储为容器 /workspace/inputs 下的真实文件。
    /// </summary>
    private (Dictionary<string, object?> Prepared, Dictionary<string, byte[]> Staged) StageInputFiles(
        Dictionary<string, object?> inputs)
    {
        var storageRoot = Path.GetFullPath(_settings.StoragePath);
        var staged = new Dictionary<string, byte[]>();
        var cachedPaths = new Dictionary<string, string>();
        long totalBytes = 0;

        object? Visit(object? value)
        {
            if (value is JsonElement element)
            {
                value = ToNative(element);
            }
            if (value is IDictionary<string, object?> dict)
            {
                if (dict.TryGetValue(InputFileKey, out var keyValue) &&
                    keyValue?.ToString() is { Length: > 0 } objectKey)
                {
                    if (!cachedPaths.TryGetValue(objectKey, out var archiveName))
                    {
                        if (cachedPaths.Count >= MaxInputFiles)
                        {
                            throw new InvalidOperationException("Too many script input files");
                        }
                        string sourcePath = SharedPath(storageRoot, objectKey, "Invalid script input file");
                        if (!File.Exists(sourcePath))
                        {
                            throw new InvalidOperationException("Script input file is unavailable");
                        }
                        long size = new FileInfo(sourcePath).Length;
                        if (size > MaxInputFileBytes)
                        {
                            throw new InvalidOperationException("Script input file exceeds the 50 MB limit");
                        }
                        totalBytes += size;
                        if (totalBytes > MaxInputFileBytesTotal)
                        {
                            throw new InvalidOperationException("Script input files exceed the 100 MB total limit");
                        }
                        string rawName = (dict.TryGetValue("filename", out var fn) && fn?.ToString() is { Length: > 0 } name
                            ? name.Replace('\\', '/')
                            : Path.GetFileName(sourcePath).Replace('\\', '/'));
                        string filename = rawName.Split('/')[^1];
                        if (string.IsNullOrEmpty(filename))
                        {
                            filename = "input.bin";
                        }
                        archiveName = $"inputs/{cachedPaths.Count + 1:0000}/{filename}";
                        cachedPaths[objectKey] = archiveName;
                        staged[archiveName] = File.ReadAllBytes(sourcePath);
                    }

                    var remapped = new Dictionary<string, object?>();
                    foreach (var (key, item) in dict)
                    {
                        if (!key.StartsWith("__ordo_", StringComparison.Ordinal))
                        {
                            remapped[key] = Visit(item);
                        }
                    }
                    remapped["path"] = $"/workspace/{archiveName}";
                    return remapped;
                }

                var visited = new Dictionary<string, object?>();
                foreach (var (key, item) in dict)
                {
                    if (!key.StartsWith("__ordo_", StringComparison.Ordinal))
                    {
                        visited[key] = Visit(item);
                    }
                }
                return visited;
            }
            if (value is System.Collections.IEnumerable enumerable && value is not string)
            {
                var list = new List<object?>();
                foreach (var item in enumerable)
                {
                    list.Add(Visit(item));
                }
                return list;
            }
            return value;
        }

        var prepared = Visit(inputs) as Dictionary<string, object?> ?? new Dictionary<string, object?>();
        return (prepared, staged);
    }

    /// <summary>
    /// 将存储根目录内的相对 POSIX 路径解析为安全的绝对路径。
    /// </summary>
    private static string SharedPath(string root, string relativePath, string message)
    {
        var parts = relativePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0 ||
            relativePath.StartsWith('/') ||
            parts.Any(p => p is "" or "." or ".."))
        {
            throw new InvalidOperationException(message);
        }

        string candidate = Path.GetFullPath(Path.Combine(new[] { root }.Concat(parts).ToArray()));
        string normalizedRoot = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (!candidate.StartsWith(normalizedRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(message);
        }
        return candidate;
    }

    /// <summary>
    /// 生成与原服务一致的文件 tar 归档（目录 0555、文件 0444）。
    /// </summary>
    private static async Task BuildArchiveAsync(Dictionary<string, byte[]> files, Stream destination)
    {
        var directories = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var name in files.Keys)
        {
            var parts = name.Split('/');
            for (int i = 1; i < parts.Length; i++)
            {
                directories.Add(string.Join('/', parts[..i]));
            }
        }

        await using var writer = new TarWriter(destination, TarEntryFormat.Pax, leaveOpen: true);
        foreach (var directory in directories.OrderBy(d => d.Count(c => c == '/'))
                     .ThenBy(d => d, StringComparer.Ordinal))
        {
            await writer.WriteEntryAsync(new PaxTarEntry(TarEntryType.Directory, directory)
            {
                Mode = UnixFileMode.UserRead | UnixFileMode.UserExecute |
                       UnixFileMode.GroupRead | UnixFileMode.GroupExecute |
                       UnixFileMode.OtherRead | UnixFileMode.OtherExecute,
            });
        }

        foreach (var (name, content) in files)
        {
            await writer.WriteEntryAsync(new PaxTarEntry(TarEntryType.RegularFile, name)
            {
                DataStream = new MemoryStream(content),
                Mode = UnixFileMode.UserRead | UnixFileMode.GroupRead | UnixFileMode.OtherRead,
            });
        }
    }

    /// <summary>
    /// 在容器内读取 /tmp/outputs 下的脚本输出文件。
    /// </summary>
    private async Task<byte[]> ReadContainerFileAsync(string containerId, string path, int limit, CancellationToken ct)
    {
        const string reader = "import os, stat, sys\n" +
            "path = sys.argv[1]\n" +
            "limit = int(sys.argv[2])\n" +
            "info = os.lstat(path)\n" +
            "if not stat.S_ISREG(info.st_mode) or info.st_size > limit:\n" +
            "    raise ValueError('invalid output file')\n" +
            "with open(path, 'rb', buffering=0) as source:\n" +
            "    while chunk := source.read(1024 * 1024):\n" +
            "        sys.stdout.buffer.write(chunk)\n";

        var client = _docker.Value;
        var exec = await client.Exec.ExecCreateContainerAsync(containerId, new ContainerExecCreateParameters
        {
            Cmd = new List<string> { _settings.SandboxPythonPath, "-c", reader, path, limit.ToString() },
            AttachStdout = true,
            AttachStderr = true,
        }, ct);

        using (var stream = await client.Exec.StartAndAttachContainerExecAsync(exec.ID, tty: false, ct))
        {
            await using var stdout = new MemoryStream();
            await using var stderr = new MemoryStream();
            await stream.CopyOutputToAsync(Stream.Null, stdout, stderr, ct);
            var inspect = await client.Exec.InspectContainerExecAsync(exec.ID, ct);
            if (inspect.ExitCode != 0)
            {
                throw new InvalidOperationException("Script output file is unavailable");
            }
            var content = stdout.ToArray();
            if (content.Length > MaxOutputFileBytes)
            {
                throw new InvalidOperationException("Script output file exceeds the 50 MB limit");
            }
            return content;
        }
    }

    /// <summary>
    /// 将 runner 声明的输出文件从容器转存到本地 artifact 目录。
    /// </summary>
    private async Task<Dictionary<string, object?>> CollectOutputArtifactsAsync(
        string containerId, Dictionary<string, object?> outputs, string jobId, CancellationToken ct)
    {
        string artifactRoot = Path.GetFullPath(_settings.SandboxArtifactPath);
        string jobDirectory = Path.Combine(artifactRoot, jobId);
        var created = new List<string>();
        int fileCount = 0;
        long totalBytes = 0;

        async Task<object?> VisitAsync(object? value)
        {
            if (value is IDictionary<string, object?> dict)
            {
                if (dict.TryGetValue(OutputFileKey, out var marker) && marker != null)
                {
                    fileCount++;
                    if (fileCount > MaxOutputFiles)
                    {
                        throw new InvalidOperationException("Too many script output files");
                    }

                    string relativeRaw = marker.ToString() ?? string.Empty;
                    var parts = relativeRaw.Split('/', StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length == 0 ||
                        relativeRaw.StartsWith('/') ||
                        parts.Any(p => p is "" or "." or ".."))
                    {
                        throw new InvalidOperationException("Invalid script output file");
                    }
                    string relative = string.Join('/', parts);

                    if (ToNativeNumber(dict.TryGetValue("size", out var declaredSize) ? declaredSize : null) is not { } size ||
                        size < 0 || size > MaxOutputFileBytes)
                    {
                        throw new InvalidOperationException("Invalid script output file size");
                    }

                    byte[] content = await ReadContainerFileAsync(containerId, $"/tmp/outputs/{relative}", MaxOutputFileBytes, ct);
                    if (content.Length != size)
                    {
                        throw new InvalidOperationException("Script output file changed during collection");
                    }
                    totalBytes += content.Length;
                    if (totalBytes > MaxOutputFileBytes)
                    {
                        throw new InvalidOperationException("Script output files exceed the 50 MB total limit");
                    }

                    Directory.CreateDirectory(jobDirectory);
                    string destination = Path.Combine(jobDirectory, Convert.ToHexString(RandomNumberGenerator.GetBytes(16)).ToLowerInvariant());
                    await File.WriteAllBytesAsync(destination, content, ct);
                    created.Add(destination);

                    string rawName = (dict.TryGetValue("filename", out var fn) && fn?.ToString() is { Length: > 0 } name
                        ? name.Replace('\\', '/')
                        : parts[^1].Replace('\\', '/'));
                    string filename = rawName.Split('/')[^1];
                    if (string.IsNullOrEmpty(filename))
                    {
                        filename = "output.bin";
                    }

                    return new Dictionary<string, object?>
                    {
                        ["filename"] = filename,
                        ["content_type"] = dict.TryGetValue("content_type", out var ctVal) && ctVal != null
                            ? ctVal.ToString()
                            : "application/octet-stream",
                        ["size"] = content.Length,
                        [ArtifactPathKey] = $"{jobId}/{Path.GetFileName(destination)}",
                    };
                }

                var visited = new Dictionary<string, object?>();
                foreach (var (key, item) in dict)
                {
                    visited[key] = await VisitAsync(item);
                }
                return visited;
            }
            if (value is System.Collections.IEnumerable enumerable && value is not string)
            {
                var list = new List<object?>();
                foreach (var item in enumerable)
                {
                    list.Add(await VisitAsync(item));
                }
                return list;
            }
            return value;
        }

        try
        {
            return await VisitAsync(outputs) as Dictionary<string, object?> ?? new Dictionary<string, object?>();
        }
        catch
        {
            foreach (var path in created)
            {
                try { File.Delete(path); } catch { }
            }
            try { Directory.Delete(jobDirectory); } catch { }
            throw;
        }
    }

    private static long? ToNativeNumber(object? value) => value switch
    {
        null => null,
        long l => l,
        int i => i,
        double d when d == Math.Floor(d) => (long)d,
        JsonElement { ValueKind: JsonValueKind.Number } el when el.TryGetInt64(out var n) => n,
        _ => long.TryParse(value.ToString(), out var parsed) ? parsed : null,
    };

    /// <summary>
    /// 将 JsonElement 递归还原为原生字典/列表/标量。
    /// </summary>
    private static object? ToNative(JsonElement element) => element.ValueKind switch
    {
        JsonValueKind.Object => element.EnumerateObject().ToDictionary(
            p => p.Name, p => ToNative(p.Value), StringComparer.Ordinal),
        JsonValueKind.Array => element.EnumerateArray().Select(ToNative).ToList(),
        JsonValueKind.String => element.GetString(),
        JsonValueKind.Number when element.TryGetInt64(out var l) => l,
        JsonValueKind.Number => element.GetDouble(),
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        JsonValueKind.Null => null,
        _ => element.ToString(),
    };

    /// <summary>
    /// 生成注入容器 /workspace/runner.py 的执行引导脚本（与原 sandbox 服务逐字一致）。
    /// </summary>
    private static string RunnerSource(SandboxExecuteRequest payload)
    {
        return RunnerTemplate
            .Replace("__MAX_LOG_BYTES__", MaxLogBytes.ToString())
            .Replace("__MAX_OUTPUT_BYTES__", MaxOutputBytes.ToString())
            .Replace("__MAX_OUTPUT_FILES__", MaxOutputFiles.ToString())
            .Replace("__MAX_OUTPUT_FILE_BYTES__", MaxOutputFileBytes.ToString())
            .Replace("__OUTPUT_FILE_KEY__", OutputFileKey)
            .Replace("__ENTRYPOINT__", payload.Entrypoint)
            .Replace("__NETWORK_ENABLED__", payload.NetworkEnabled ? "True" : "False");
    }

    private const string RunnerTemplate = """
import asyncio, importlib, importlib.util, inspect, io, json, os, sys, time, traceback
from pathlib import Path, PurePosixPath
MAX_LOG_BYTES = __MAX_LOG_BYTES__
MAX_OUTPUT_BYTES = __MAX_OUTPUT_BYTES__
MAX_OUTPUT_FILES = __MAX_OUTPUT_FILES__
MAX_OUTPUT_FILE_BYTES = __MAX_OUTPUT_FILE_BYTES__
OUTPUT_FILE_KEY = '__OUTPUT_FILE_KEY__'
OUTPUT_DIR = Path("/tmp/outputs")
original_stdout = sys.stdout
log_bytes = 0
logs_truncated = False

def emit(event):
    original_stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    original_stdout.flush()

class EventWriter(io.TextIOBase):
    def __init__(self, stream):
        self.stream = stream
        self.buffer = ""
    def write(self, value):
        global log_bytes, logs_truncated
        self.buffer += str(value)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            encoded = line.encode("utf-8", errors="replace")
            remaining = MAX_LOG_BYTES - log_bytes
            if remaining > 0:
                clipped = encoded[:remaining].decode("utf-8", errors="replace")
                emit({"type": "log", "stream": self.stream, "message": clipped})
                log_bytes += min(len(encoded), remaining)
            if len(encoded) > remaining:
                logs_truncated = True
        return len(value)
    def flush(self):
        if self.buffer:
            self.write("\n")

def output_file(path, filename=None, content_type=None):
    candidate = Path(path).resolve()
    root = OUTPUT_DIR.resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Output files must be created inside context['output_dir']") from exc
    return {
        OUTPUT_FILE_KEY: relative.as_posix(),
        "filename": PurePosixPath(str(filename or relative.name).replace("\\", "/")).name,
        "content_type": str(content_type or "application/octet-stream"),
    }

def normalize_output_files(value, state):
    if isinstance(value, dict) and value.get(OUTPUT_FILE_KEY):
        relative = PurePosixPath(str(value[OUTPUT_FILE_KEY]))
        if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("Invalid script output file")
        path = (OUTPUT_DIR / Path(*relative.parts)).resolve()
        if not path.is_relative_to(OUTPUT_DIR.resolve()) or not path.is_file():
            raise ValueError("Script output file is unavailable")
        size = path.stat().st_size
        state["count"] += 1
        state["bytes"] += size
        if state["count"] > MAX_OUTPUT_FILES:
            raise ValueError("Too many script output files")
        if size > MAX_OUTPUT_FILE_BYTES or state["bytes"] > MAX_OUTPUT_FILE_BYTES:
            raise ValueError("Script output files exceed the 50 MB limit")
        return {
            OUTPUT_FILE_KEY: relative.as_posix(),
            "filename": PurePosixPath(str(value.get("filename") or relative.name).replace("\\", "/")).name,
            "content_type": str(value.get("content_type") or "application/octet-stream"),
            "size": size,
        }
    if isinstance(value, dict):
        return {key: normalize_output_files(item, state) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_output_files(item, state) for item in value]
    return value

sys.path.insert(0, "/workspace")
sys.stdout = EventWriter("stdout")
sys.stderr = EventWriter("stderr")
try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entrypoint = '__ENTRYPOINT__'
    if ":" in entrypoint:
        module_name, function_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
    else:
        function_name = entrypoint
        spec = importlib.util.spec_from_file_location("main", "/workspace/main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    function = getattr(module, function_name)
    inputs = json.load(open("/workspace/input.json", encoding="utf-8"))
    context = {
        "temp_dir": "/tmp",
        "input_dir": "/workspace/inputs",
        "output_dir": str(OUTPUT_DIR),
        "output_file": output_file,
        "network_enabled": __NETWORK_ENABLED__,
    }
    result = function(inputs, context)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if not isinstance(result, dict):
        raise TypeError("Python entrypoint must return an object")
    output_state = {"count": 0, "bytes": 0}
    result = normalize_output_files(result, output_state)
    sys.stdout.flush()
    sys.stderr.flush()
    serialized = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
    if len(serialized) > MAX_OUTPUT_BYTES:
        raise ValueError("Script output exceeds the 2 MB limit")
    emit({"type": "result", "status": "succeeded", "outputs": result, "error": None, "logs_truncated": logs_truncated})
    if output_state["count"]:
        while True:
            time.sleep(60)
except Exception:
    sys.stdout.flush()
    sys.stderr.flush()
    emit({"type": "result", "status": "failed", "outputs": {}, "error": traceback.format_exc()[-32000:], "logs_truncated": logs_truncated})
""";
}
