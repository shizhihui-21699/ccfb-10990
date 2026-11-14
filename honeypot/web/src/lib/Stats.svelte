<script>
  import { onMount } from 'svelte'
  import { api } from '../api.js'

  let stats = $state(null)
  let error = $state('')
  let timer

  async function load() {
    try {
      stats = await api.stats()
      error = ''
    } catch (e) {
      error = String(e)
    }
  }

  onMount(() => {
    load()
    timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  })

  const max = (rows) => Math.max(1, ...(rows || []).map((r) => r.n))
</script>

{#if error}<p class="err">{error}</p>{/if}

{#if stats}
  <div class="cards">
    <div class="card"><div class="num">{stats.totals.sessions}</div><div class="lbl">总会话</div></div>
    <div class="card"><div class="num">{stats.totals.ssh_sessions}</div><div class="lbl">SSH 会话</div></div>
    <div class="card"><div class="num">{stats.totals.http_sessions}</div><div class="lbl">HTTP 会话</div></div>
    <div class="card"><div class="num">{stats.totals.auth_attempts}</div><div class="lbl">认证尝试</div></div>
    <div class="card"><div class="num">{stats.totals.unique_ips}</div><div class="lbl">独立 IP</div></div>
  </div>

  <div class="grid">
    <section>
      <h3>来源 IP 排行</h3>
      {#each stats.top_ips as r}
        <div class="row">
          <span class="mono ip">{r.ip}</span>
          <div class="bar"><div style="width:{(r.n / max(stats.top_ips)) * 100}%"></div></div>
          <span class="n">{r.n}</span>
          <span class="dim">ssh:{r.ssh} http:{r.http}</span>
        </div>
      {:else}<p class="dim">暂无数据</p>{/each}
    </section>

    <section>
      <h3>常用口令排行</h3>
      {#each stats.top_passwords as r}
        <div class="row">
          <span class="mono pw">{r.password}</span>
          <div class="bar red"><div style="width:{(r.n / max(stats.top_passwords)) * 100}%"></div></div>
          <span class="n">{r.n}</span>
        </div>
      {:else}<p class="dim">暂无数据</p>{/each}
    </section>

    <section>
      <h3>常用用户名</h3>
      {#each stats.top_usernames as r}
        <div class="row">
          <span class="mono pw">{r.username}</span>
          <div class="bar"><div style="width:{(r.n / max(stats.top_usernames)) * 100}%"></div></div>
          <span class="n">{r.n}</span>
        </div>
      {:else}<p class="dim">暂无数据</p>{/each}
    </section>

    <section>
      <h3>HTTP 探测路径</h3>
      {#each stats.top_http_paths as r}
        <div class="row">
          <span class="mono pw">{r.path}</span>
          <div class="bar"><div style="width:{(r.n / max(stats.top_http_paths)) * 100}%"></div></div>
          <span class="n">{r.n}</span>
        </div>
      {:else}<p class="dim">暂无数据</p>{/each}
    </section>
  </div>
{/if}

<style>
  .cards { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
  .card { background: #161d28; border: 1px solid #232b35; border-radius: 8px; padding: 14px 22px; min-width: 110px; }
  .num { font-size: 26px; font-weight: 700; color: #7cc4ff; }
  .lbl { font-size: 12px; color: #7d8a99; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  section { background: #161d28; border: 1px solid #232b35; border-radius: 8px; padding: 14px 18px; }
  h3 { margin: 0 0 12px; font-size: 14px; color: #9aa7b4; }
  .row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 13px; }
  .mono { font-family: ui-monospace, Menlo, monospace; }
  .ip { width: 130px; }
  .pw { width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .n { width: 36px; text-align: right; color: #7cc4ff; }
  .dim { color: #5c6a7a; font-size: 12px; }
  .bar { flex: 1; height: 10px; background: #0f1419; border-radius: 5px; overflow: hidden; }
  .bar > div { height: 100%; background: #1d6ce0; }
  .bar.red > div { background: #d64545; }
  .err { color: #ff7a7a; }
</style>
