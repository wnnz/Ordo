using System.Text.Json;
using System.Text.RegularExpressions;

namespace Ordo.Backend.Engine.Values;

/// <summary>
/// 工作流上下文变量解析与表达式计算器。
/// </summary>
public static class WorkflowValueEvaluator
{
    private static readonly Regex VariableRegex = new(@"\{\{\s*([^{}\r\n]+?)\s*\}\}", RegexOptions.Compiled);

    /// <summary>
    /// 对字符串中的 {{node.field}} 变量进行递归插值。
    /// </summary>
    public static object? ResolveVariables(object? input, Dictionary<string, object?> context)
    {
        if (input == null) return null;

        if (input is string str)
        {
            var trimmed = str.Trim();
            // 如果整行只有一个变量占位符，例如 "{{start.image}}"，直接返回底层原始对象而不是转换为字符串
            var fullMatch = VariableRegex.Match(trimmed);
            if (fullMatch.Success && fullMatch.Value == trimmed)
            {
                string path = fullMatch.Groups[1].Value.Trim();
                return ReadContextPath(context, path);
            }

            // 多个变量或混合字符串插值
            return VariableRegex.Replace(str, match =>
            {
                string path = match.Groups[1].Value.Trim();
                var val = ReadContextPath(context, path);
                return val switch
                {
                    null => string.Empty,
                    string s => s,
                    _ => JsonSerializer.Serialize(val)
                };
            });
        }

        if (input is JsonElement elem)
        {
            return ResolveJsonElement(elem, context);
        }

        if (input is IDictionary<string, object?> dict)
        {
            var res = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
            foreach (var kvp in dict)
            {
                res[kvp.Key] = ResolveVariables(kvp.Value, context);
            }
            return res;
        }

        if (input is not string && input is System.Collections.IEnumerable enumerable)
        {
            var list = new List<object?>();
            foreach (var item in enumerable)
            {
                list.Add(ResolveVariables(item, context));
            }
            return list;
        }

        return input;
    }

    private static object? ResolveJsonElement(JsonElement elem, Dictionary<string, object?> context)
    {
        switch (elem.ValueKind)
        {
            case JsonValueKind.String:
                return ResolveVariables(elem.GetString(), context);
            case JsonValueKind.Number:
                if (elem.TryGetInt64(out long l)) return l;
                return elem.GetDouble();
            case JsonValueKind.True: return true;
            case JsonValueKind.False: return false;
            case JsonValueKind.Null: return null;
            case JsonValueKind.Array:
                return elem.EnumerateArray().Select(item => ResolveJsonElement(item, context)).ToList();
            case JsonValueKind.Object:
                var dict = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
                foreach (var prop in elem.EnumerateObject())
                {
                    dict[prop.Name] = ResolveJsonElement(prop.Value, context);
                }
                return dict;
            default:
                return elem.ToString();
        }
    }

    /// <summary>
    /// 从上下文中按照 a.b.c 或 a[0] 的点号路径提取数据。
    /// </summary>
    public static object? ReadContextPath(Dictionary<string, object?> context, string path)
    {
        if (string.IsNullOrWhiteSpace(path)) return null;

        string[] parts = path.Split('.', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length == 0) return null;

        if (!context.TryGetValue(parts[0], out var current))
        {
            return null;
        }

        for (int i = 1; i < parts.Length; i++)
        {
            if (current == null) return null;
            current = ReadProperty(current, parts[i]);
        }

        return current;
    }

    private static object? ReadProperty(object obj, string propertyName)
    {
        if (obj is JsonElement je)
        {
            if (je.ValueKind == JsonValueKind.Object && je.TryGetProperty(propertyName, out var prop))
            {
                return prop;
            }
            return null;
        }

        if (obj is IDictionary<string, object?> dict)
        {
            return dict.TryGetValue(propertyName, out var val) ? val : null;
        }

        var propInfo = obj.GetType().GetProperty(propertyName);
        if (propInfo != null)
        {
            return propInfo.GetValue(obj);
        }

        return null;
    }

    /// <summary>
    /// 评估条件分支节点。
    /// </summary>
    public static bool EvaluateCondition(Dictionary<string, object?> config, Dictionary<string, object?> context)
    {
        // 提取 conditions 数组与 logical_operator (and / or)
        if (!config.TryGetValue("conditions", out var rawConditions) || rawConditions is not IEnumerable<object?> conditions)
        {
            return true;
        }

        string logicalOp = config.TryGetValue("logical_operator", out var lop) ? lop?.ToString()?.ToLowerInvariant() ?? "and" : "and";

        foreach (var item in conditions)
        {
            if (item is not IDictionary<string, object?> cond) continue;

            object? leftVal = ResolveVariables(cond.TryGetValue("variable", out var v) ? v : null, context);
            string op = cond.TryGetValue("comparison_operator", out var cop) ? cop?.ToString()?.ToLowerInvariant() ?? "equals" : "equals";
            object? rightVal = ResolveVariables(cond.TryGetValue("value", out var rv) ? rv : null, context);

            bool matched = CompareValues(leftVal, op, rightVal);

            if (logicalOp == "or" && matched) return true;
            if (logicalOp == "and" && !matched) return false;
        }

        return logicalOp == "and";
    }

    private static bool CompareValues(object? left, string op, object? right)
    {
        string leftStr = left?.ToString() ?? string.Empty;
        string rightStr = right?.ToString() ?? string.Empty;

        return op switch
        {
            "equals" or "==" => string.Equals(leftStr, rightStr, StringComparison.OrdinalIgnoreCase),
            "not_equals" or "!=" => !string.Equals(leftStr, rightStr, StringComparison.OrdinalIgnoreCase),
            "contains" => leftStr.Contains(rightStr, StringComparison.OrdinalIgnoreCase),
            "not_contains" => !leftStr.Contains(rightStr, StringComparison.OrdinalIgnoreCase),
            "starts_with" => leftStr.StartsWith(rightStr, StringComparison.OrdinalIgnoreCase),
            "ends_with" => leftStr.EndsWith(rightStr, StringComparison.OrdinalIgnoreCase),
            "is_empty" => string.IsNullOrWhiteSpace(leftStr),
            "is_not_empty" => !string.IsNullOrWhiteSpace(leftStr),
            "greater_than" or ">" => double.TryParse(leftStr, out var l) && double.TryParse(rightStr, out var r) && l > r,
            "less_than" or "<" => double.TryParse(leftStr, out var l2) && double.TryParse(rightStr, out var r2) && l2 < r2,
            _ => false
        };
    }
}
