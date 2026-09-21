using Ordo.Backend.Engine.Models;
using Ordo.Backend.Engine.Values;

namespace Ordo.Backend.Engine.Executors;

/// <summary>
/// 分类选择分支节点执行器。
/// </summary>
public class ClassifierNodeExecutor : INodeExecutor
{
    public string NodeType => "classifier";

    public Task<object?> ExecuteAsync(WorkflowNode node, Dictionary<string, object?> context, CancellationToken ct)
    {
        object? inputVal = WorkflowValueEvaluator.ResolveVariables(node.Data.TryGetValue("input", out var inp) ? inp : null, context);
        string inputStr = inputVal?.ToString() ?? "";

        string matchedCategory = "default";
        if (node.Data.TryGetValue("categories", out var rawCats) && rawCats is IEnumerable<object?> categories)
        {
            foreach (var cat in categories)
            {
                if (cat is IDictionary<string, object?> dict)
                {
                    string name = dict.TryGetValue("name", out var n) ? n?.ToString() ?? "" : "";
                    if (dict.TryGetValue("keywords", out var kw) && kw is IEnumerable<object?> keywords)
                    {
                        if (keywords.Any(k => k != null && inputStr.Contains(k.ToString()!, StringComparison.OrdinalIgnoreCase)))
                        {
                            matchedCategory = name;
                            break;
                        }
                    }
                }
            }
        }

        return Task.FromResult<object?>(new Dictionary<string, object?>
        {
            { "category", matchedCategory },
            { "branch", matchedCategory }
        });
    }
}
