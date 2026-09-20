namespace OrdoWindowsAgent.Native;

/// <summary>
/// WTS 查询会话信息类型枚举。
/// </summary>
internal enum WtsInfoClass
{
    /// <summary>
    /// 查询与会话关联的用户名。
    /// </summary>
    WtsUserName = 5,

    /// <summary>
    /// 查询会话的客户端协议类型 (0=Console, 1=ICA, 2=RDP)。
    /// </summary>
    WtsClientProtocolType = 16
}
