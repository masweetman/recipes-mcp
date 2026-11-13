# recipes-mcp

An MCP server that lets an AI assistant search a curated list of food blogs and extract clean, structured recipes from them. Pair it with an AnyList MCP server: this server finds and reads recipes, and the AnyList server imports them, schedules meals and builds shopping lists.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_sites` | Lists the blogs that can be searched. |
| `search_recipes` | Searches one or all blogs and returns titles, URLs and snippets. |
| `get_recipe` | Fetches a recipe URL and returns title, ingredients, instructions, times, yield and image. |

How it works:

- Search uses each blog's WordPress REST API or Blogger feed when available, and falls back to a bundled SearXNG instance restricted to the blog's domain.
- `get_recipe` only fetches URLs on the allowlisted domains in [blogs.yaml](blogs.yaml). It resolves only to public IPs, revalidates every redirect, caps the response at 5 MB and checks the content type.
- Pages without recipe schema (for example Food Wishes) return `structured: false` plus the page text.
- The endpoint is protected by a secret token in the URL path.

To add or remove blogs, edit [blogs.yaml](blogs.yaml).

## Ports

Both are internal to the Docker network and are not published to the host.

| Service | Port |
| --- | --- |
| recipes-mcp | 8001 |
| SearXNG | 8081 |

## Deploy with Portainer

Prerequisites: Docker host with Portainer, Nginx Proxy Manager (NPM) running on the same host, and this repository in a Git remote Portainer can reach.

1. Generate two secrets:

   ```sh
   openssl rand -hex 32   # MCP_PATH_TOKEN
   openssl rand -hex 32   # SEARXNG_SECRET
   ```

2. Find the name of the Docker network NPM is attached to (Portainer > Networks; commonly `npm_default`).
3. In Portainer go to **Stacks > Add stack > Repository**.
   - Repository URL: your Git URL (add credentials if private)
   - Reference: `refs/heads/main`
   - Compose path: `docker-compose.yml`
4. Under **Environment variables** add:

   | Name | Value |
   | --- | --- |
   | `MCP_PATH_TOKEN` | secret from step 1 |
   | `SEARXNG_SECRET` | secret from step 1 |
   | `PUBLIC_HOST` | your public hostname, e.g. `recipesmcp.example.com` |
   | `NPM_NETWORK` | NPM network name from step 2 |
   | `LOG_LEVEL` | optional, default `INFO` |

   See [.env.example](.env.example).
5. Click **Deploy the stack**. Portainer builds both images and starts the containers.
6. Check that `recipes-mcp` is healthy in the container list.

`PUBLIC_HOST` must match the hostname clients use, because the server rejects other `Host` headers.

## Proxy with Nginx Proxy Manager

1. Create a DNS record for your hostname pointing at the Docker host.
2. In NPM go to **Hosts > Proxy Hosts > Add Proxy Host**.
   - Domain Names: the same value as `PUBLIC_HOST`
   - Scheme: `http`
   - Forward Hostname / IP: `recipes-mcp`
   - Forward Port: `8001`
   - Block Common Exploits: on
3. On the **SSL** tab request a Let's Encrypt certificate and enable **Force SSL**.
4. On the **Advanced** tab add:

   ```nginx
   proxy_buffering off;
   proxy_read_timeout 300s;
   ```

5. Verify:

   ```sh
   curl https://<PUBLIC_HOST>/healthz   # ok
   ```

The MCP endpoint is `https://<PUBLIC_HOST>/mcp/<MCP_PATH_TOKEN>`. Treat this URL as a password. Requests to any other path return 404.

## Use with an AI tool

### Claude.ai

1. Go to **Settings > Connectors > Add custom connector**.
2. Name: `Recipes`. URL: `https://<PUBLIC_HOST>/mcp/<MCP_PATH_TOKEN>`.
3. Leave authentication empty and save.
4. Enable the connector in a chat, alongside your AnyList connector.

### VS Code

Add to `.vscode/mcp.json` (or the user-level MCP config):

```json
{
  "servers": {
    "recipes": {
      "type": "http",
      "url": "https://<PUBLIC_HOST>/mcp/<MCP_PATH_TOKEN>"
    }
  }
}
```

### Example prompts

- "Find three weeknight chicken dinners from my recipe blogs and add them to AnyList."
- "Search Serious Eats for a sourdough pancake recipe, then add the ingredients to my shopping list."

## Local development

```sh
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
MCP_PATH_TOKEN=dev .venv/bin/python -m recipes_mcp   # http://localhost:8001/mcp/dev
```

Outside Docker, set `SEARXNG_URL` to a reachable SearXNG instance; without one, blogs that need it return no search results.

## Rotating the token

Change `MCP_PATH_TOKEN` in the Portainer stack, redeploy, and update the URL in each client.
