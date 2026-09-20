using System.Runtime.InteropServices;

namespace OrdoWindowsAgent.Native;

/// <summary>
/// 映射 Win32 WTS_SESSION_INFOW 结构。
/// </summary>
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
internal struct WtsSessionInfo
{
    /// <summary>
    /// 会话数字 ID。
    /// </summary>
    public int SessionId;

    /// <summary>
    /// 指向会话名称字符串指针（如 RDP-Tcp#0）。
    /// </summary>
    public IntPtr pWinStationName;

    /// <summary>
    /// 会话连接状态。
    /// </summary>
    public WtsConnectStateClass State;
}
