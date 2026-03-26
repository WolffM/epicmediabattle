# Cookie Authentication

Some image sources require authentication. Place cookie files here.

## Structure

```
cookies/
├── <source_name>/
│   ├── cookies.json    # Browser-exported cookies
│   └── login.json      # Credentials (username, api_key)
```

## How to Export Cookies

1. Log into the source site in your browser
2. Use a cookie export extension (e.g., "Cookie-Editor")
3. Export as JSON to `cookies/<source>/cookies.json`

## login.json Format

```json
{
  "username": "your_username",
  "api_key": "your_api_key"
}
```

**WARNING:** Never commit real credentials to git!
