const origFetch = (globalThis as any).fetch;
(globalThis as any).fetch = async (url: any, opts: any) => {
  const t0 = Date.now();
  const body = opts && opts.body ? String(opts.body) : '';
  const tag = typeof url === 'string' && url.includes('ollama') ? 'OLLAMA' : 'CLOUD';
  try {
    const res = await origFetch(url, opts);
    const clone = res.clone();
    let text = '';
    try {
      text = await clone.text();
    } catch (e) {
      text = '<body-read-error>';
    }
    console.log(
      `[${tag}] status=${res.status} ok=${res.ok} elapsed=${Date.now() - t0}ms bodyLen=${text.length} bodyHead=${text
        .replace(/\s+/g, ' ')
        .slice(0, 400)}`
    );
    if (tag === 'CLOUD') {
      console.log(`[CLOUD] reqHead=${body.replace(/\s+/g, ' ').slice(0, 300)}`);
    }
    return res;
  } catch (e: any) {
    console.log(`[${tag}] THROW after ${Date.now() - t0}ms: ${e && e.message ? e.message : e}`);
    throw e;
  }
};

import { ClaudeAPI, VISUAL_TUTOR_SYSTEM_PROMPT } from '../src/ClaudeAPI';

const PNG1PX =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

async function main() {
  const api = new ClaudeAPI();
  console.log(`model=${api.model}`);
  for (const prompt of [
    'Explain how binary search works like I am 10 years old.',
    'Generate a clean folder structure for a React + FastAPI web app.',
    'Teach me JavaScript Promises.',
  ]) {
    console.log(`\n=== PROMPT: ${prompt.slice(0, 60)}`);
    const capture = {
      label: 'screen',
      screenshotWidthInPixels: 1,
      screenshotHeightInPixels: 1,
      imageDataBase64: PNG1PX,
    } as any;
    const out = await api.analyzeImageStreaming([capture], VISUAL_TUTOR_SYSTEM_PROMPT, [], prompt);
    console.log(`RESULT len=${out.length} head=${out.replace(/\s+/g, ' ').slice(0, 300)}`);
  }
  console.log('DIAG_DONE');
}

main().catch((e) => {
  console.error('DIAG_ERROR', e);
  process.exit(1);
});
