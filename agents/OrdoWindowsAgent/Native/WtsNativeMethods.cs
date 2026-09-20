using System.Runtime.InteropServices;

namespace OrdoWindowsAgent.Native;

/// <summary>
/// 封装 wtsapi32.dll 的 Win32 原生调用。
/// </summary>
internal static class WtsNativeMethods
{
    /// <summary>
    /// 当前终端服务器句柄常量。
    /// </summary>
    public static readonly IntPtr WtsCurrentServerHandle = IntPtr.Zero;

    /// <summary>
    /// 枚举指定远程桌面服务器上的会话。
    /// </summary>
    [DllImport("wtsapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool WTSEnumerateSessionsW(
        IntPtr hServer,
        int reserved,
        int version,
        out IntPtr ppSessionInfo,
        out int pCount);

    /// <summary>
    /// 释放 WTS API 分配的非托管内存。
    /// </summary>
    [DllImport("wtsapi32.dll")]
    public static extern void WTSFreeMemory(IntPtr pMemory);

    /// <summary>
    /// 查询指定会话的属性信息。
    /// </summary>
    [DllImport("wtsapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool WTSQuerySessionInformationW(
        IntPtr hServer,
        int sessionId,
        WtsInfoClass wtsInfoClass,
        out IntPtr ppBuffer,
        out int pBytesReturned);

    /// <summary>
    /// 断开指定的终端服务会话连接（不注销）。
    /// </summary>
    [DllImport("wtsapi32.dll", SetLastError = true)]
    public static extern bool WTSDisconnectSession(
        IntPtr hServer,
        int sessionId,
        bool bWait);
}
