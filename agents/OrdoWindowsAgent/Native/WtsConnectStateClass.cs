namespace OrdoWindowsAgent.Native;

/// <summary>
/// Windows 终端服务 (WTS) 会话连接状态枚举。
/// </summary>
internal enum WtsConnectStateClass
{
    /// <summary>
    /// 用户登录并在控制台或远程处于活动状态。
    /// </summary>
    WtsActive = 0,

    /// <summary>
    /// 会话已连接但可能处于锁定等状态。
    /// </summary>
    WtsConnected = 1,

    /// <summary>
    /// 会话正在连接握手中。
    /// </summary>
    WtsConnectQuery = 2,

    /// <summary>
    /// 会话正在被远程阴影监视中。
    /// </summary>
    WtsShadow = 3,

    /// <summary>
    /// 用户断开连接但进程仍在后台运行。
    /// </summary>
    WtsDisconnected = 4,

    /// <summary>
    /// 会话空闲。
    /// </summary>
    WtsIdle = 5,

    /// <summary>
    /// 会话正在侦听新连接。
    /// </summary>
    WtsListen = 6,

    /// <summary>
    /// 会话正在重置中。
    /// </summary>
    WtsReset = 7,

    /// <summary>
    /// 会话处于下线状态。
    /// </summary>
    WtsDown = 8,

    /// <summary>
    /// 会话处于初始化状态。
    /// </summary>
    WtsInit = 9
}
