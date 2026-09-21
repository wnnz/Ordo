namespace Ordo.Backend.Engine;

/// <summary>
/// 工作流节点执行器注册中心。
/// </summary>
public class NodeRegistry
{
    private readonly Dictionary<string, INodeExecutor> _executors;

    public NodeRegistry(IEnumerable<INodeExecutor> executors)
    {
        _executors = executors.ToDictionary(e => e.NodeType.ToLowerInvariant(), e => e);
    }

    /// <summary>
    /// 获取指定类型的执行器。
    /// </summary>
    public INodeExecutor? GetExecutor(string nodeType)
    {
        return _executors.TryGetValue(nodeType.ToLowerInvariant(), out var executor) ? executor : null;
    }

    /// <summary>
    /// 是否支持该节点类型。
    /// </summary>
    public bool IsSupported(string nodeType)
    {
        return _executors.ContainsKey(nodeType.ToLowerInvariant());
    }
}
