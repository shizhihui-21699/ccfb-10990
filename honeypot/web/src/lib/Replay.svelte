<script>
  import { onMount } from 'svelte'
  import { api } from '../api.js'

  let { sessionId } = $props()

  let detail = $state(null)
  let segments = $state([]) // 终端渲染片段 {kind:'out'|'in'|'http', text}
  let playing = $state(false)
  let speed = $state(1)
  let curMs = $state(0)
  let totalMs = $state(0)
  let idx = $state(0) // 下一个待播事件下标
  let error = $state('')

  const TYPE_MS = 30 // 每个输入字符的敲键间隔(再除以倍速)

  onMount(async () => {
    try {
      detail = await api.session(sessionId)
      const evs = detail.events
      totalMs = evs.length ? evs[evs.length - 1].t_ms + 300 : 0
    } catch (e) {
      error = String(e)
    }
  })

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

  function appendSeg(kind, text) {
    segments = [...segments, { kind, text }]
  }

  async function typeIn(text) {
    // 逐字敲入,模拟真人打字节奏
    segments = [...segments, { kind: 'in', text: '' }]
    for (const ch of text) {
      if (!playing) return
      segments[segments.length - 1].text += ch
      await sleep(TYPE_MS / speed)
    }
  }

  async function playFrom(startIdx) {
    let lastT = startIdx > 0 ? detail.events[startIdx - 1].t_ms : 0
    for (let i = startIdx; i < detail.events.length && playing; i++) {
      const ev = detail.events[i]
      const wait = Math.max(0, (ev.t_ms - lastT) / speed)
      if (wait > 0) await sleep(wait)
      if (!playing) break
      if (ev.type === 'in') {
        await typeIn(ev.data)
        appendSeg('echo', '\n')
      } else if (ev.type === 'http') {
        appendSeg('http', formatHttp(ev.data))
      } else {
        appendSeg('out', ev.data)
      }
      curMs = ev.t_ms
      lastT = ev.t_ms
      idx = i + 1
    }
    if (idx >= (detail?.events.length ?? 0)) playing = false
  }

  function formatHttp(data) {
    try {
      const r = JSON.parse(data)
      let s = `${r.method} ${r.path}\n`
      for (const [k, v] of Object.entries(r.headers || {})) s += `  ${k}: ${v}\n`
      if (r.body) s += `  body: ${r.body}\n`
      return s
    } catch {
      return data + '\n'
    }
  }

  function play() {
    if (!detail) return
    if (idx >= detail.events.length) restart()
    playing = true
    playFrom(idx)
  }
  function pause() { playing = false }

  function restart() {
    playing = false
    segments = []
    idx = 0
    curMs = 0
    play()
  }

  function seek(e) {
    const t = Number(e.target.value)
    playing = false
    // 即时重建 t 时刻之前的全部内容
    const evs = detail.events
    const segs = []
    let i = 0
    for (; i < evs.length && evs[i].t_ms <= t; i++) {
      const ev = evs[i]
      if (ev.type === 'in') { segs.push({ kind: 'in', text: ev.data }); segs.push({ kind: 'echo', text: '\n' }) }
      else if (ev.type === 'http') segs.push({ kind: 'http', text: formatHttp(ev.data) })
      else segs.push({ kind: 'out', text: ev.data })
    }
    segments = segs
    idx = i
    curMs = t
  }

  const fmtTs = (ts) => new Date(ts * 1000).toLocaleString()
</script>

{#if error}<p class="err">{error}</p>{/if}

{#if detail}
  <div class="meta">
    <span class="badge">{detail.session.protocol.toUpperCase()}</span>
    <span class="mono">{detail.session.src_ip}:{detail.session.src_port}</span>
    <span>{fmtTs(detail.session.start_ts)}</span>
    {#if detail.session.meta}
      {@const m = JSON.parse(detail.session.meta)}
      {#if m.client_version}<span class="dim mono">{m.client_version}</span>{/if}
      {#if m.user_agent}<span class="dim">{m.user_agent}</span>{/if}
    {/if}
  </div>

  {#if detail.auth_attempts.length}
    <div class="auths">
      <b>认证尝试:</b>
      {#each detail.auth_attempts as a}
        <code>{a.username} / {a.password}</code>
      {/each}
    </div>
  {/if}

  <div class="controls">
    <button onclick={playing ? pause : play}>{playing ? '⏸ 暂停' : '▶ 播放'}</button>
    <button onclick={restart}>⟲ 重播</button>
    <select bind:value={speed}>
      {#each [0.5, 1, 2, 4, 8] as s}<option value={s}>{s}x</option>{/each}
    </select>
    <input type="range" min="0" max={totalMs} value={curMs} oninput={seek} />
    <span class="mono dim">{(curMs / 1000).toFixed(1)}s / {(totalMs / 1000).toFixed(1)}s</span>
  </div>

  <pre class="term">{#each segments as seg}<span class={seg.kind}>{seg.text}</span>{/each}<span class="cursor" class:blink={!playing}>█</span></pre>
{/if}

<style>
  .meta { display: flex; gap: 14px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
  .badge { background: #144a75; color: #7cc4ff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
  .mono { font-family: ui-monospace, Menlo, monospace; }
  .dim { color: #7d8a99; font-size: 13px; }
  .auths { margin-bottom: 10px; font-size: 13px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .auths code { background: #2a1f1f; color: #ffb3b3; padding: 2px 8px; border-radius: 4px; }
  .controls { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
  .controls button, .controls select {
    background: #1a2230; color: #d7dde4; border: 1px solid #2c3644;
    padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
  }
  .controls input[type='range'] { flex: 1; accent-color: #1d6ce0; }
  .term {
    background: #0a0e14; border: 1px solid #232b35; border-radius: 8px;
    padding: 14px; min-height: 380px; max-height: 60vh; overflow-y: auto;
    font-family: ui-monospace, Menlo, monospace; font-size: 13px; line-height: 1.45;
    white-space: pre-wrap; word-break: break-all; margin: 0;
  }
  .term .out { color: #c5d0dc; }
  .term .in { color: #7ee787; font-weight: 600; }
  .term .echo { color: #c5d0dc; }
  .term .http { color: #e3b341; }
  .cursor { color: #7ee787; }
  .blink { animation: b 1s step-start infinite; }
  @keyframes b { 50% { opacity: 0; } }
  .err { color: #ff7a7a; }
</style>
