using System.Runtime.InteropServices;

namespace OrdoWindowsAgent.Native;

/// <summary>
/// 封装 iphlpapi.dll 的网络与路由原生调用。
/// </summary>
internal static class IpHelperNativeMethods
{
    /// <summary>
    /// 获取到达指定目标 IPv4 地址的最佳路由网络接口索引。
    /// </summary>
    /// <param name="destAddr">目标 IPv4 地址整数。</param>
    /// <param name="bestIfIndex">最佳接口索引输出。</param>
    /// <returns>错误代码，0 表示成功。</returns>
    [DllImport("iphlpapi.dll", ExactSpelling = true)]
    public static extern int GetBestInterface(uint destAddr, out uint bestIfIndex);
}
