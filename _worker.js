// Cloudflare Pages Worker to route domains to specific subfolders
export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        const host = url.hostname;

        // Optionally, ignore routing for the default pages.dev domain
        if (host.endsWith('pages.dev')) {
            return env.ASSETS.fetch(request);
        }

        // New Secure API Route for updating notices
        if (request.method === 'POST' && url.pathname === '/api/update-notice') {
            try {
                const body = await request.json();
                const { host: reqHost, password, noticeData } = body;

                // 0. Resolve folder from host using dealers.json
                const mappingRes = await env.ASSETS.fetch(new Request(new URL('/dealers.json', request.url)));
                if (!mappingRes.ok) return new Response(JSON.stringify({ error: "Dealers configuration missing" }), { status: 500 });
                const mapping = await mappingRes.json();
                const folder = mapping[reqHost];
                if (!folder) return new Response(JSON.stringify({ error: "Domain not registered" }), { status: 404 });

                // 1. Fetch the secret.json for this specific dealer folder
                const secretRes = await env.ASSETS.fetch(new Request(new URL(`/dealers/${folder}/secret.json`, request.url)));
                if (!secretRes.ok) return new Response(JSON.stringify({ error: "Dealer not found or unconfigured" }), { status: 404 });
                
                const secret = await secretRes.json();
                
                // 2. Verify password
                if (secret.password !== password) {
                    return new Response(JSON.stringify({ error: "Invalid Dealer Password" }), { status: 401 });
                }

                // 3. Update GitHub using the secure Worker env variable
                const githubToken = env.GITHUB_TOKEN; // Set this in Cloudflare dashboard
                if (!githubToken) return new Response(JSON.stringify({ error: "Server missing GitHub Token" }), { status: 500 });

                const repoOwner = env.GITHUB_OWNER || 'YOUR_GITHUB_USERNAME'; // E.g., from env or hardcode
                const repoName = env.GITHUB_REPO || 'YOUR_REPO_NAME';
                const filePath = `dealers/${folder}/notice.json`;
                const githubUrl = `https://api.github.com/repos/${repoOwner}/${repoName}/contents/${filePath}`;

                // Get current file SHA
                const getRes = await fetch(githubUrl, {
                    headers: { "Authorization": `token ${githubToken}`, "User-Agent": "Cloudflare-Worker" }
                });
                
                let sha = null;
                if (getRes.ok) {
                    const fileData = await getRes.json();
                    sha = fileData.sha;
                }

                // Push new file content
                const contentBase64 = btoa(unescape(encodeURIComponent(JSON.stringify(noticeData, null, 2))));
                const putRes = await fetch(githubUrl, {
                    method: "PUT",
                    headers: {
                        "Authorization": `token ${githubToken}`,
                        "Content-Type": "application/json",
                        "User-Agent": "Cloudflare-Worker"
                    },
                    body: JSON.stringify({
                        message: `Update notice for ${folder}`,
                        content: contentBase64,
                        sha: sha
                    })
                });

                if (putRes.ok) {
                    return new Response(JSON.stringify({ success: true }), { status: 200 });
                } else {
                    const err = await putRes.json();
                    return new Response(JSON.stringify({ error: err.message || "Failed to save to GitHub" }), { status: 500 });
                }

            } catch (err) {
                return new Response(JSON.stringify({ error: "Server Error" }), { status: 500 });
            }
        }

        try {
            // 1. Fetch dealers.json to find domain mapping
            // In a Pages Worker, we can fetch from the deployed assets
            const mappingUrl = new URL('/dealers.json', request.url);
            const mappingRes = await env.ASSETS.fetch(mappingUrl);
            
            if (mappingRes.ok) {
                const mapping = await mappingRes.json();
                
                // 2. Check if the current domain exists in mapping
                if (mapping[host]) {
                    const folderName = mapping[host]; // e.g. "dhansri-motors"
                    
                    // Rewrite URL to serve from the dealer's folder
                    const newPath = `/dealers/${folderName}${url.pathname === '/' ? '/index.html' : url.pathname}`;
                    
                    return env.ASSETS.fetch(new Request(new URL(newPath, request.url), request));
                }
            }
        } catch (e) {
            console.error("Worker error:", e);
        }

        // 3. Fallback: serve normally if no mapping found
        return env.ASSETS.fetch(request);
    }
};
