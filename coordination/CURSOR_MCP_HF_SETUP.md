# Cursor + Hugging Face MCP Setup Guide

**Verified:** All URLs below returned HTTP 200 at time of writing.  
**Applies to:** Cursor v1.0+ (June 2025+), HF MCP Server as of July 2025.

---

## What This Gives You

Once wired up, Cursor's Agent can call these [HF MCP built-in tools](https://huggingface.co/docs/hub/en/agents-mcp) directly:

| Tool | What it does |
|---|---|
| **Model Search** | Search HF Hub models with filters for task, library, etc. |
| **Dataset Search** | Search datasets with filters for author, tags, etc. |
| **Spaces Semantic Search** | Find AI Apps via natural language |
| **Papers Semantic Search** | Find ML research papers |
| **Documentation Semantic Search** | Search HF docs (transformers, PEFT, etc.) |
| **Hub Repository Details** | Get full metadata for any model/dataset/space — optionally include README |
| **Run and Manage Jobs** | Run, monitor, and schedule jobs on HF infrastructure |

You can also add any [Gradio Space with an MCP badge](https://huggingface.co/docs/hub/en/spaces-mcp-servers) as an additional tool (push to Spaces, run inference, etc.).

The HF MCP Server is **live and public** at `https://huggingface.co/mcp`. It runs as a stateless Streamable HTTP server — no local process to maintain. Source: [HF blog post on building the server](https://huggingface.co/blog/building-hf-mcp).

---

## What the HF MCP Server Does NOT Do Out of the Box

The seven built-in tools above are **read and job-management** oriented. Direct "push model weights" or "push dataset files" via MCP are not exposed as built-in tools — those operations go through the [HF Hub Python API](https://huggingface.co/docs/huggingface_hub) or `git push`. To wire upload/push workflows into Cursor MCP, you add a custom Gradio Space as an MCP tool (see Step 4b).

---

## Prerequisites

- Cursor v1.0 or later (MCP OAuth shipped in v1.0, June 2025)
- A Hugging Face account
- An HF access token (token scope discussed below)
- macOS, Linux, or Windows

---

## Step 1: Get or Confirm Your HF Token

Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

**Token scope required:**

| Operation | Minimum scope |
|---|---|
| Search models, datasets, spaces, papers | `read` |
| Hub Repository Details (private repos) | `read` |
| Run and Manage Jobs | `write` (jobs need to write to HF infra) |
| Push to Spaces / models | `write` |
| Org resources (e.g. SZLHOLDINGS org) | `write` + org membership with write role |

Your existing SZLHOLDINGS write token covers all of these. Per the [HF token docs](https://huggingface.co/docs/hub/en/security-tokens): write tokens grant read + write access to repos you have write access to; org membership role governs org-level access.

**Recommended:** Create a dedicated fine-grained token for MCP with only the permissions you actually need. Fine-grained tokens are safer for production and can be scoped to specific repos or orgs.

To create or copy your token:
1. Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Click **New token** → choose **write** (or fine-grained scoped to your org)
3. Copy the `hf_...` value — you will need it below

---

## Step 2: Add the HF MCP Server to Cursor

Cursor stores MCP config in one of two places:

| Scope | Path |
|---|---|
| **Global** (all projects) | `~/.cursor/mcp.json` |
| **Project-only** | `.cursor/mcp.json` in the repo root |

Project-level wins if the same server is defined in both. For SZLHOLDINGS work, global config is usually the right choice.

### Method A — Via Cursor UI (Recommended for First Setup)

1. Open Cursor
2. Press `Cmd+Shift+J` (macOS) or `Ctrl+Shift+J` (Windows/Linux) to open Cursor Settings
3. Click the **Tools & Integrations** tab (also reachable via `Cursor Settings → Tools & MCP`)
4. Click **Add new global MCP server** — this opens (or creates) `~/.cursor/mcp.json`
5. Paste the JSON from Method B below into the `mcpServers` object, save, and restart Cursor

### Method B — Direct File Edit

Open or create `~/.cursor/mcp.json`. The recommended config uses **OAuth** (Cursor v1.0+), which avoids storing your token in plaintext:

```json
{
  "mcpServers": {
    "hugging-face": {
      "url": "https://huggingface.co/mcp"
    }
  }
}
```

With this config, Cursor detects that `huggingface.co/mcp` requires auth, shows a **Connect** button in Settings → Tools & MCP, and opens a browser OAuth flow when you click it. Your token is stored securely by Cursor and never written to disk in plaintext. Source: [Cursor MCP auth guide](https://www.truefoundry.com/blog/mcp-authentication-in-cursor-oauth-api-keys-and-secure-configuration).

**Alternative — Static Bearer Token (if OAuth flow fails):**

```json
{
  "mcpServers": {
    "hugging-face": {
      "url": "https://huggingface.co/mcp",
      "headers": {
        "Authorization": "Bearer ${env:HF_TOKEN}"
      }
    }
  }
}
```

The `${env:HF_TOKEN}` syntax tells Cursor to read the value from your shell environment at runtime — your token never sits in the JSON file. Set it in your shell profile:

```bash
# ~/.zshrc or ~/.bashrc
export HF_TOKEN="hf_your_token_here"
```

Then reload: `source ~/.zshrc`

**Do not paste the raw `hf_...` value directly into mcp.json** — if that file ever touches version control, the token leaks.

### Which transport does Cursor use?

Cursor v1.0+ supports **Streamable HTTP** natively. The HF MCP server runs Streamable HTTP in production (deployed July 2025). No `mcp-remote` proxy or `npx` wrapper is required. Earlier Cursor versions (pre-1.0) required the `mcp-remote` workaround; if you are on an older version, upgrade Cursor first.

---

## Step 3: Verify the Server Is Connected

After saving `mcp.json` and restarting Cursor:

1. Open **Cursor Settings → Tools & MCP** (or `Cmd+Shift+J` → Tools & Integrations)
2. Look for **hugging-face** in the server list
3. Expected status: green dot, tool count shown (expect 7+ built-in tools)

If you used the OAuth-only config (no headers):
- The server will show a blue **Connect** button and "Needs authentication" label
- Click **Connect** → browser opens HF login → authorize → Cursor shows green

You can also trigger the MCP tool list from the Agent:

```
@hugging-face list available tools
```

The Agent should return the seven built-in tool names from the table in the intro.

**Check MCP logs for raw connection status:**

1. Open `View → Output` (or `Cmd+Shift+U`)
2. Select **MCP** from the output channel dropdown
3. Look for lines like:
   ```
   [info] Found 7 tools, 4 prompts, and 0 resources
   [info] Successfully connected to stdio server
   ```

---

## Step 4a: First Tool Test — Search SZLHOLDINGS Datasets

With Cursor Agent active (the chat panel, with the agent model selected), type:

```
Search Hugging Face datasets owned by SZLHOLDINGS
```

or

```
Use the HF Dataset Search tool to find all datasets under the SZLHOLDINGS organization
```

Expected: The Agent calls the **Dataset Search** tool and returns a list of datasets with names, download counts, and Hub links. If no datasets are found for the org, try:

```
Search HF Hub for models in the SZLHOLDINGS organization
```

To fetch full details on a specific repo:

```
Get Hub Repository Details for SZLHOLDINGS/your-model-name including the README
```

---

## Step 4b: Extend With Spaces Tools (Push, Inference, Upload)

The built-in tools cover search and metadata. To push files to a Space or run model inference from Cursor, add a Gradio Space as an MCP tool:

1. Go to [huggingface.co/settings/mcp](https://huggingface.co/settings/mcp) (while logged in)
2. Browse [Spaces with MCP support](https://huggingface.co/spaces?filter=mcp-server) and add the ones you need
3. Restart Cursor — new Space tools appear automatically

The Spaces MCP endpoint pattern for a custom Space is:
```
https://YOUR-USERNAME-space-name.hf.space/gradio_api/mcp/sse
```

To add a specific Space directly in `mcp.json`:

```json
{
  "mcpServers": {
    "hugging-face": {
      "url": "https://huggingface.co/mcp"
    },
    "my-hf-space": {
      "url": "https://szlholdings-your-space.hf.space/gradio_api/mcp/sse",
      "headers": {
        "Authorization": "Bearer ${env:HF_TOKEN}"
      }
    }
  }
}
```

To build your own MCP-enabled Gradio Space (for push/upload workflows):

```python
import gradio as gr

def push_to_hub(repo_id: str, file_path: str) -> str:
    """Push a file to a Hugging Face repository.
    
    Args:
        repo_id: Repository ID in format 'owner/name'
        file_path: Local path to file to push
    
    Returns:
        URL of the uploaded file
    """
    from huggingface_hub import HfApi
    api = HfApi()
    url = api.upload_file(path_or_fileobj=file_path, repo_id=repo_id, path_in_repo=file_path)
    return url

demo = gr.Interface(fn=push_to_hub, inputs=["text", "text"], outputs="text")
demo.launch(mcp_server=True)  # Exposes MCP schema automatically
```

Push this to a Gradio Space; it will receive the MCP badge and become callable from Cursor. Source: [Spaces as MCP servers guide](https://huggingface.co/docs/hub/en/spaces-mcp-servers).

---

## Step 5: Security Hygiene

### Never commit a token to mcp.json

Use `${env:HF_TOKEN}` in the config and export the token from your shell profile or a secrets manager. The env-var syntax is supported in both `headers` (remote servers) and `env` (stdio servers).

To verify your mcp.json is safe to commit:

```bash
grep -n "hf_" ~/.cursor/mcp.json
```

If that returns any matches, replace the literal token with `${env:HF_TOKEN}`.

### Token rotation

When rotating:
1. Generate the new token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Update `HF_TOKEN` in your shell profile (or secrets manager) and reload: `source ~/.zshrc`
3. Revoke the old token on the HF tokens page
4. Restart Cursor so it re-reads the env

If you used Cursor's OAuth flow (the no-token config), Cursor manages token refresh automatically. You only need to re-authorize if you revoke the OAuth grant on HF.

### Prefer OAuth over static tokens for remote servers

The OAuth path (`"url": "https://huggingface.co/mcp"` with no headers) is the recommended approach per the [MCP auth spec](https://www.truefoundry.com/blog/mcp-authentication-in-cursor-oauth-api-keys-and-secure-configuration). OAuth tokens expire and can be scoped; static tokens do not expire and carry more risk.

### Scope tokens to the minimum needed

If you only need search/read operations in Cursor, use a `read`-scope token rather than write. Reserve write tokens for pipelines that actually push data.

### Add mcp.json to .gitignore (as a fallback)

If you ever need a literal token in mcp.json for debugging:

```bash
echo "~/.cursor/mcp.json" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global
```

---

## Troubleshooting

### Tools discovered but not usable in Agent

**Symptom:** Cursor MCP logs show `Found 12 tools, 4 prompts` but the Agent says it has no HF tools.

**Cause:** This is a known Cursor bug ([forum thread](https://forum.cursor.com/t/cursor-agent-unable-to-use-the-huggingface-mcp-tools/144441)) where tools are discovered but not exposed to the AI agent runtime when there are duplicate server entries or residual config state.

**Fix:**
1. Check for duplicate server entries in both `~/.cursor/mcp.json` and `.cursor/mcp.json` in your project root
2. Remove duplicates — keep only one definition
3. Fully quit and relaunch Cursor (not just reload window)
4. Check Settings → Tools & MCP and manually toggle the HF server off and back on

### Connection refused / server not found

**Symptom:** MCP log shows connection errors against `https://huggingface.co/mcp`.

**Diagnosis:**
```bash
curl -s -o /dev/null -w "%{http_code}" https://huggingface.co/mcp
```
Should return `200`. If it returns `000` or `502`, check your network / proxy settings.

**Fix:** Ensure outbound HTTPS to `huggingface.co` is allowed. If behind a corporate proxy, check whether Cursor respects `HTTPS_PROXY` env var.

### Authentication error (401)

**Symptom:** MCP log shows `401 Unauthorized` or Agent says "authentication failed".

**Fix:**
1. Verify your token is valid: `curl -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami`
2. Check the token has not expired or been revoked at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
3. If using `${env:HF_TOKEN}`, confirm the env var is set: `echo $HF_TOKEN` in a new terminal
4. Restart Cursor after updating the env var — Cursor reads env at launch, not dynamically

### 403 on org resources

**Symptom:** Searches succeed for public repos but fail for SZLHOLDINGS private resources.

**Cause:** Token may be read-only when write is needed, or the org has enforced fine-grained tokens only.

**Fix:** Check the org's token policy at `huggingface.co/organizations/SZLHOLDINGS/settings` (admin access required). If fine-grained tokens are enforced, create a fine-grained token with explicit access to SZLHOLDINGS repos.

### SSE transport errors (older Cursor)

**Symptom:** Errors like `SSE transport not supported` or connection drops.

**Context:** The HF MCP Server uses Streamable HTTP in production, not legacy SSE. Older MCP clients default to SSE-only and fail.

**Fix:** Upgrade Cursor to v1.0+ (Streamable HTTP support). As a workaround on older versions, use `mcp-remote` as a proxy:

```json
{
  "mcpServers": {
    "hugging-face": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@0.1.16",
        "https://huggingface.co/mcp",
        "--header",
        "Authorization: Bearer ${env:HF_TOKEN}"
      ]
    }
  }
}
```

Note: pin `mcp-remote` to `0.1.16` or later (CVE-2025-6514 affected earlier versions).

### ZeroGPU quota exhausted when running Space tools

**Symptom:** Space tool calls fail with a quota error.

**Fix:** ZeroGPU quota is per-account. Upgrade to HF Pro for 40 minutes/day (8× free tier). Check usage at `huggingface.co/settings/billing`.

---

## Reference Links (all verified live)

| Resource | URL |
|---|---|
| HF MCP Server landing page | https://huggingface.co/mcp |
| HF MCP settings (generate config snippets) | https://huggingface.co/settings/mcp |
| HF Hub MCP documentation | https://huggingface.co/docs/hub/en/agents-mcp |
| Spaces as MCP servers | https://huggingface.co/docs/hub/en/spaces-mcp-servers |
| HF blog: building the MCP server | https://huggingface.co/blog/building-hf-mcp |
| HF token management | https://huggingface.co/settings/tokens |
| HF token scope docs | https://huggingface.co/docs/hub/en/security-tokens |
| Cursor MCP auth guide (TrueFoundry) | https://www.truefoundry.com/blog/mcp-authentication-in-cursor-oauth-api-keys-and-secure-configuration |
| Cursor MCP setup guide (Natoma) | https://natoma.ai/blog/how-to-enabling-mcp-in-cursor |
| mcp-remote npm package | https://www.npmjs.com/package/mcp-remote |
