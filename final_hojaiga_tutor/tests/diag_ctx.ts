import { VISUAL_TUTOR_SYSTEM_PROMPT } from '../src/ClaudeAPI';

const PNG1PX =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

async function call(label: string, extra: Record<string, any>) {
  const t0 = Date.now();
  const body: any = {
    model: 'qwen2.5vl:3b',
    stream: false,
    messages: [
      { role: 'system', content: VISUAL_TUTOR_SYSTEM_PROMPT },
      {
        role: 'user',
        content: 'screen (image dimensions: 1x1 pixels)\n\nExplain how binary search works like I am 10 years old.',
        images: [PNG1PX],
      },
    ],
    ...extra,
  };
  try {
    const res = await fetch('http://127.0.0.1:11434/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let content = '';
    try {
      content = JSON.parse(text)?.message?.content ?? '';
    } catch {
      content = text;
    }
    console.log(
      `[${label}] status=${res.status} elapsed=${Date.now() - t0}ms contentLen=${String(content).length} head=${String(
        content
      )
        .replace(/\s+/g, ' ')
        .slice(0, 220)}`
    );
  } catch (e: any) {
    console.log(`[${label}] THROW ${e && e.message}`);
  }
}

async function main() {
  await call('NO_OPTIONS', {});
  await call('NUM_CTX_8192', { options: { num_ctx: 8192 } });
  await call('NUM_CTX_16384', { options: { num_ctx: 16384 } });
  console.log('CTX_DONE');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
