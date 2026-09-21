using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading.Channels;

namespace Ordo.Backend.Services;

/// <summary>
/// 进程内工作流运行事件发布与流式订阅服务（替代 Redis Pub/Sub 与 Redis Stream）。
/// </summary>
public class RunEventsService
{
    private sealed class RunEventBus
    {
        public List<string> History { get; } = new();
        public List<Channel<string>> Subscribers { get; } = new();
        public object Lock { get; } = new();
        public DateTime LastAccess { get; set; } = DateTime.UtcNow;
    }

    private readonly ConcurrentDictionary<string, RunEventBus> _buses = new();

    public RunEventsService()
    {
        // 启动后台定时器清理过期超过 24 小时的事件总线
        _ = PeriodicCleanupAsync();
    }

    /// <summary>
    /// 发布一个运行事件（如节点开始、节点完成、状态变更）。
    /// </summary>
    public void PublishRunEvent(string runId, object eventData)
    {
        string json = eventData is string s ? s : JsonSerializer.Serialize(eventData);
        var bus = _buses.GetOrAdd(runId, _ => new RunEventBus());

        lock (bus.Lock)
        {
            bus.LastAccess = DateTime.UtcNow;
            if (bus.History.Count < 5000)
            {
                bus.History.Add(json);
            }

            for (int i = bus.Subscribers.Count - 1; i >= 0; i--)
            {
                var ch = bus.Subscribers[i];
                if (!ch.Writer.TryWrite(json))
                {
                    // 队列已满或已关闭则移除
                }
            }
        }
    }

    /// <summary>
    /// 为客户端建立 SSE 流式异步枚举器。
    /// </summary>
    public async IAsyncEnumerable<string> StreamRunEventsAsync(string runId, string initialStatus, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var bus = _buses.GetOrAdd(runId, _ => new RunEventBus());
        var channel = Channel.CreateBounded<string>(new BoundedChannelOptions(1000)
        {
            FullMode = BoundedChannelFullMode.DropOldest
        });

        List<string> replayEvents;
        lock (bus.Lock)
        {
            bus.LastAccess = DateTime.UtcNow;
            replayEvents = new List<string>(bus.History);
            bus.Subscribers.Add(channel);
        }

        try
        {
            // 1. 发送初始状态事件
            yield return $"data: {JsonSerializer.Serialize(new { type = "status", status = initialStatus })}\n\n";

            if (initialStatus is "succeeded" or "failed" or "waiting" or "cancelled")
            {
                yield break;
            }

            // 2. 回放历史事件
            foreach (var ev in replayEvents)
            {
                yield return $"data: {ev}\n\n";
                if (ev.Contains("\"type\":\"run_finished\""))
                {
                    yield break;
                }
            }

            // 3. 消费实时事件
            while (!ct.IsCancellationRequested)
            {
                using var timeoutCts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, timeoutCts.Token);

                string? ev = null;
                bool isTimeout = false;
                try
                {
                    ev = await channel.Reader.ReadAsync(linkedCts.Token);
                }
                catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested)
                {
                    isTimeout = true;
                }

                if (isTimeout)
                {
                    yield return ": keep-alive\n\n";
                    continue;
                }

                if (ev != null)
                {
                    yield return $"data: {ev}\n\n";
                    if (ev.Contains("\"type\":\"run_finished\""))
                    {
                        yield break;
                    }
                }
            }
        }
        finally
        {
            lock (bus.Lock)
            {
                bus.Subscribers.Remove(channel);
            }
        }
    }

    private async Task PeriodicCleanupAsync()
    {
        while (true)
        {
            await Task.Delay(TimeSpan.FromHours(1));
            var cutoff = DateTime.UtcNow.AddHours(-24);
            foreach (var kvp in _buses)
            {
                if (kvp.Value.LastAccess < cutoff)
                {
                    _buses.TryRemove(kvp.Key, out _);
                }
            }
        }
    }
}
