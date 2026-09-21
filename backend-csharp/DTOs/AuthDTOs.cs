using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

namespace Ordo.Backend.DTOs;

public class RegisterRequest
{
    [Required]
    [EmailAddress]
    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;

    [Required]
    [MinLength(6)]
    [JsonPropertyName("password")]
    public string Password { get; set; } = string.Empty;

    [Required]
    [JsonPropertyName("display_name")]
    public string DisplayName { get; set; } = string.Empty;
}

public class LoginRequest
{
    [Required]
    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;

    [Required]
    [JsonPropertyName("password")]
    public string Password { get; set; } = string.Empty;
}

public class UserResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;

    [JsonPropertyName("display_name")]
    public string DisplayName { get; set; } = string.Empty;

    [JsonPropertyName("is_active")]
    public bool IsActive { get; set; }

    [JsonPropertyName("is_platform_admin")]
    public bool IsPlatformAdmin { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class TokenResponse
{
    [JsonPropertyName("access_token")]
    public string AccessToken { get; set; } = string.Empty;

    [JsonPropertyName("token_type")]
    public string TokenType { get; set; } = "bearer";

    [JsonPropertyName("user")]
    public UserResponse User { get; set; } = null!;
}
