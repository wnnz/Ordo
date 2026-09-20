using System.ComponentModel;
using System.Runtime.InteropServices;

namespace OrdoWindowsAgent;

/// <summary>
/// 负责管理 Windows 远程桌面 (RDP) 会话的枚举与安全断开。
/// </summary>
public static class RdpManager
{
    private static readonly IntPtr WtsCurrentServerHandle = IntPtr.Zero;

    private static readonly Dictionary<int, string> SessionStateNames = new()
    {
        { 0, "active" },
        { 1, "connected" },
        { 2, "connect_query" },
        { 3, "shadow" },
        { 4, "disconnected" },
        { 5, "idle" },
        { 6, "listening" },
        { 7, "reset" },
        { 8, "down" },
        { 9, "initializing" }
    };

    /// <summary>
    /// 枚举当前活动的 RDP 会话。
    /// </summary>
    /// <returns>RDP 会话信息列表。</returns>
    public static List<RdpSessionInfo> ListSessions()
    {
        var sessions = new List<RdpSessionInfo>();

        if (!WTSEnumerateSessionsW(WtsCurrentServerHandle, 0, 1, out var pSessionInfo, out var count))
        {
            return sessions;
        }

        try
        {
            int structSize = Marshal.SizeOf<WTS_SESSION_INFOW>();
            for (int i = 0; i < count; i++)
            {
                var sessionInfo = Marshal.PtrToStructure<WTS_SESSION_INFOW>(pSessionInfo + (i * structSize));
                int stateInt = (int)sessionInfo.State;

                // 仅筛选 active (0) 和 connected (1) 状态
                if (stateInt != 0 && stateInt != 1)
                {
                    continue;
                }

                // 检查协议类型是否为 RDP (协议类型 2)
                int protocol = QuerySessionProtocol(sessionInfo.SessionId);
                if (protocol != 2)
                {
                    continue;
                }

                string username = QuerySessionUserName(sessionInfo.SessionId);
                string winStationName = Marshal.PtrToStringUni(sessionInfo.pWinStationName) ?? string.Empty;
                string stateName = SessionStateNames.TryGetValue(stateInt, out var name) ? name : stateInt.ToString();

                sessions.Add(new RdpSessionInfo
                {
                    SessionId = sessionInfo.SessionId,
                    Username = username,
                    SessionName = winStationName,
                    State = stateName
                });
            }
        }
        finally
        {
            WTSFreeMemory(pSessionInfo);
        }

        return sessions;
    }

    /// <summary>
    /// 断开指定的 RDP 会话，若未指定则断开所有活动 RDP 会话。
    /// </summary>
    /// <param name="targetSessionId">可选的目标会话 ID。</param>
    /// <returns>断开操作结果。</returns>
    public static RdpDisconnectResponse DisconnectSessions(int? targetSessionId = null)
    {
        var activeSessions = ListSessions();

        if (targetSessionId.HasValue)
        {
            activeSessions = activeSessions.Where(s => s.SessionId == targetSessionId.Value).ToList();
            if (activeSessions.Count == 0)
            {
                throw new KeyNotFoundException($"RDP session {targetSessionId.Value} is not active or connected");
            }
        }

        var disconnected = new List<RdpSessionInfo>();
        var failed = new List<RdpDisconnectFailure>();

        foreach (var session in activeSessions)
        {
            if (WTSDisconnectSession(WtsCurrentServerHandle, session.SessionId, false))
            {
                disconnected.Add(session);
            }
            else
            {
                var error = new Win32Exception(Marshal.GetLastWin32Error()).Message;
                failed.Add(new RdpDisconnectFailure
                {
                    SessionId = session.SessionId,
                    Username = session.Username,
                    SessionName = session.SessionName,
                    State = session.State,
                    Error = error
                });
            }
        }

        return new RdpDisconnectResponse
        {
            Ok = failed.Count == 0,
            DisconnectedCount = disconnected.Count,
            Sessions = disconnected,
            Failed = failed,
            Message = $"Disconnected {disconnected.Count} RDP session(s) without logging off users.",
            Source = "windows-host-agent"
        };
    }

    private static int QuerySessionProtocol(int sessionId)
    {
        if (!WTSQuerySessionInformationW(WtsCurrentServerHandle, sessionId, WTS_INFO_CLASS.WTSClientProtocolType, out var pBuffer, out _))
        {
            return -1;
        }

        try
        {
            return Marshal.ReadInt16(pBuffer);
        }
        finally
        {
            WTSFreeMemory(pBuffer);
        }
    }

    private static string QuerySessionUserName(int sessionId)
    {
        if (!WTSQuerySessionInformationW(WtsCurrentServerHandle, sessionId, WTS_INFO_CLASS.WTSUserName, out var pBuffer, out _))
        {
            return string.Empty;
        }

        try
        {
            return Marshal.PtrToStringUni(pBuffer) ?? string.Empty;
        }
        finally
        {
            WTSFreeMemory(pBuffer);
        }
    }

    [DllImport("wtsapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool WTSEnumerateSessionsW(
        IntPtr hServer,
        int reserved,
        int version,
        out IntPtr ppSessionInfo,
        out int pCount);

    [DllImport("wtsapi32.dll")]
    private static extern void WTSFreeMemory(IntPtr pMemory);

    [DllImport("wtsapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool WTSQuerySessionInformationW(
        IntPtr hServer,
        int sessionId,
        WTS_INFO_CLASS wtsInfoClass,
        out IntPtr ppBuffer,
        out int pBytesReturned);

    [DllImport("wtsapi32.dll", SetLastError = true)]
    private static extern bool WTSDisconnectSession(
        IntPtr hServer,
        int sessionId,
        bool bWait);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WTS_SESSION_INFOW
    {
        public int SessionId;
        public IntPtr pWinStationName;
        public WTS_CONNECTSTATE_CLASS State;
    }

    private enum WTS_CONNECTSTATE_CLASS
    {
        WTSActive = 0,
        WTSConnected = 1,
        WTSConnectQuery = 2,
        WTSShadow = 3,
        WTSDisconnected = 4,
        WTSIdle = 5,
        WTSListen = 6,
        WTSReset = 7,
        WTSDown = 8,
        WTSInit = 9
    }

    private enum WTS_INFO_CLASS
    {
        WTSUserName = 5,
        WTSClientProtocolType = 16
    }
}
