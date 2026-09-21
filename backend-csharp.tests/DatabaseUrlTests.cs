using Xunit;

namespace Ordo.Backend.Tests;

public class DatabaseUrlTests
{
    [Fact]
    public void TestSqlAlchemyUrlConversion()
    {
        string asyncpgUrl = "postgresql+asyncpg://ordo:mypassword@shared-postgres:5432/ordo_db";
        // 验证反射或相同算法的转换
        var uri = new Uri("postgres://" + asyncpgUrl["postgresql+asyncpg://".Length..]);
        var userInfo = uri.UserInfo.Split(':');

        Assert.Equal("ordo", userInfo[0]);
        Assert.Equal("mypassword", userInfo[1]);
        Assert.Equal("shared-postgres", uri.Host);
        Assert.Equal(5432, uri.Port);
        Assert.Equal("ordo_db", uri.AbsolutePath.TrimStart('/'));
    }
}
