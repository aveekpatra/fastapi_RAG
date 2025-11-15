# API Key Security Guide

This document explains how to configure and use API key authentication for the Czech Legal Assistant API, with emphasis on the security measures implemented to protect the API.

## Security Features Implemented

The API includes multiple security layers to protect against common vulnerabilities:

1. **API Key Authentication**: All endpoints require a valid API key
2. **Rate Limiting**: Prevents abuse and resource exhaustion attacks
3. **Security Headers**: Additional protection against XSS, clickjacking, and other attacks
4. **CORS Configuration**: Controls which domains can access the API

## Configuration

1. Open the `.env` file in the project root directory.
2. Add or modify the `API_KEY` variable:
   ```
   API_KEY=your_secure_api_key_here
   ```
3. Replace `your_secure_api_key_here` with a strong, unique API key.
4. Restart the application for the changes to take effect.

## Usage

All secured endpoints require authentication using one of two methods:

### Method 1: Bearer Token (Recommended)

Include the API key in the Authorization header as a Bearer token:

```http
Authorization: Bearer your_secure_api_key_here
```

Example using curl:
```bash
curl -X POST "http://localhost:8000/web-search" \
     -H "Authorization: Bearer your_secure_api_key_here" \
     -H "Content-Type: application/json" \
     -d '{"question": "Jaké jsou právní důsledky neplacení nájmu?", "top_k": 5}'
```

### Method 2: Query Parameter

Include the API key as a query parameter named `api_key`:

```
/api_endpoint?question=...&api_key=your_secure_api_key_here
```

Example using curl:
```bash
curl -X GET "http://localhost:8000/web-search-stream?question=Jaké%20jsou%20právní%20důsledky%20neplacení%20nájmu&api_key=your_secure_api_key_here"
```

## Development

If no API key is set in the `.env` file (or the `API_KEY` variable is empty), the endpoints will not require authentication. This is useful for development purposes.

## Security Best Practices

1. **Generate a strong API key**: Use a random string of at least 32 characters with a mix of letters, numbers, and special characters.
2. **Keep the API key secret**: Never commit the API key to version control or share it publicly.
3. **Rotate API keys regularly**: Change your API keys periodically for enhanced security.
4. **Use HTTPS**: Always use HTTPS when transmitting API keys to prevent interception.
5. **Monitor usage**: Track API usage to detect any unauthorized access.
6. **Use Bearer tokens**: Prefer Bearer token authentication over query parameters to prevent API key exposure in logs.
7. **Configure allowed origins**: Set the ALLOWED_ORIGINS environment variable to restrict API access to specific domains.

## Troubleshooting

### 401 Unauthorized Error

If you receive a 401 Unauthorized error:

1. Verify that the API key is correctly set in the `.env` file
2. Check that you're using the correct authentication method
3. Ensure the API key is included exactly as configured (no extra spaces)
4. For Bearer token authentication, verify the header format: `Authorization: Bearer your_api_key`

### API Key Not Working

1. Restart the application after changing the `.env` file
2. Check for any typos in the API key
3. Verify the API key is loaded correctly by checking the application logs
4. Ensure the API key is set - the API now requires an API key to be configured in production

### Rate Limit Exceeded

If you receive a 429 Too Many Requests error:
1. Reduce the frequency of your requests
2. Consider implementing client-side rate limiting
3. For streaming endpoints, implement backoff strategies

### CORS Issues

If you encounter CORS errors:
1. Verify your domain is included in the ALLOWED_ORIGINS environment variable
2. For development, you can temporarily set ALLOWED_ORIGINS to "*" but change this in production

## Endpoint Access Levels & Rate Limits

| Endpoint | Authentication Required | Rate Limit |
|----------|-------------------------|------------|
| /health | Yes | 60/minute |
| /web-search | Yes | 10/minute |
| /web-search-stream | Yes | 5/minute |
| /case-search | Yes | 10/minute |
| /case-search-stream | Yes | 5/minute |
| /combined-search | Yes | 5/minute |
| /combined-search-stream | Yes | 2/minute |
| /search-cases | Yes | 20/minute |
| /search-cases-stream | Yes | 10/minute |
| /debug/qdrant | Yes | 5/minute |

## Security Headers

The API automatically includes the following security headers in all responses:

- `X-Content-Type-Options: nosniff` - Prevents MIME-type sniffing
- `X-Frame-Options: DENY` - Prevents clickjacking
- `X-XSS-Protection: 1; mode=block` - Enables XSS protection
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` - Enforces HTTPS