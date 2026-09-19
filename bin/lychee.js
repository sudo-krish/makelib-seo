#!/usr/bin/env node
/**
 * Cross-platform runner and fallback shim for lychee link checker.
 * Prefers system native 'lychee' binary if present in PATH or .bin/.
 * Falls back to an internal recursive link and anchor-hash crawler
 * if the binary is unavailable.
 */

const { spawnSync } = require('child_process');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const path = require('path');

const args = process.argv.slice(2);

function runNativeLychee() {
  const binaryCandidates = [
    '/usr/bin/lychee',
    '/usr/local/bin/lychee',
    `${process.env.HOME}/.cargo/bin/lychee`,
    `${process.env.HOME}/.local/bin/lychee`,
  ];
  for (const bin of binaryCandidates) {
    try {
      if (path.resolve(bin) === path.resolve(__filename)) continue;
      const check = spawnSync(bin, ['--version'], { stdio: 'ignore' });
      if (check.status === 0) {
        const result = spawnSync(bin, args, { stdio: 'inherit' });
        process.exit(result.status ?? 0);
      }
    } catch {
      // Continue to next candidate
    }
  }
  return false;
}

// Fallback internal link & anchor checker
async function runInternalLinkChecker() {
  const targetArg = args.find(a => !a.startsWith('-')) || 'http://localhost:3000';
  console.log(`[lychee-shim] Native lychee binary not found. Running built-in link & anchor checker on ${targetArg}...`);

  let targetUrl;
  try {
    targetUrl = new URL(targetArg);
  } catch (err) {
    console.error(`[lychee-shim] Invalid URL provided: ${targetArg}`);
    process.exit(1);
  }

  const visited = new Set();
  const queue = [targetUrl.pathname || '/'];
  let errorCount = 0;

  function fetchUrl(urlPath) {
    return new Promise((resolve) => {
      const client = targetUrl.protocol === 'https:' ? https : http;
      const reqUrl = new URL(urlPath, targetUrl.origin);
      const req = client.get(reqUrl, { timeout: 5000 }, (res) => {
        let body = '';
        res.on('data', chunk => { body += chunk; });
        res.on('end', () => {
          resolve({ status: res.statusCode, headers: res.headers, body });
        });
      });
      req.on('error', (err) => {
        resolve({ status: 500, error: err.message, body: '' });
      });
      req.on('timeout', () => {
        req.destroy();
        resolve({ status: 408, error: 'Timeout', body: '' });
      });
    });
  }

  while (queue.length > 0) {
    const currentPath = queue.shift();
    if (visited.has(currentPath)) continue;
    visited.add(currentPath);

    const res = await fetchUrl(currentPath);
    if (res.status >= 400) {
      console.error(`  [BROKEN LINK] ${targetUrl.origin}${currentPath} returned HTTP ${res.status}`);
      errorCount++;
      continue;
    }
    console.log(`  [OK] ${targetUrl.origin}${currentPath} (HTTP ${res.status})`);

    // Parse HTML for internal links and check anchor hashes
    if (res.headers && String(res.headers['content-type']).includes('text/html')) {
      const domIds = new Set();
      const idMatches = res.body.matchAll(/id=["']([^"']+)["']/gi);
      for (const m of idMatches) {
        domIds.add(m[1]);
      }

      const hrefMatches = res.body.matchAll(/<a\s+[^>]*href=["']([^"']+)["']/gi);
      for (const m of hrefMatches) {
        const href = m[1].trim();
        if (href.startsWith('#')) {
          const hashId = href.slice(1);
          if (hashId && !domIds.has(hashId)) {
            console.error(`  [BROKEN ANCHOR] On ${currentPath}: Anchor '#${hashId}' not found in DOM.`);
            errorCount++;
          }
        } else if (href.startsWith('/') && !href.startsWith('//')) {
          const cleanPath = href.split('#')[0];
          if (!visited.has(cleanPath) && !queue.includes(cleanPath)) {
            queue.push(cleanPath);
          }
        }
      }
    }
  }

  if (errorCount > 0) {
    console.error(`\n[lychee-shim] Crawl failed with ${errorCount} broken link(s)/anchor(s).`);
    process.exit(1);
  } else {
    console.log(`\n[lychee-shim] All ${visited.size} crawled link(s) and anchor hashes are healthy.`);
    process.exit(0);
  }
}

if (!runNativeLychee()) {
  runInternalLinkChecker();
}
