<script>
  import { onMount } from 'svelte'
  import { api } from '../api.js'

  let { onSelect } = $props()
  let sessions = $state([])
  let error = $state('')
  let timer

  async function load() {
    try {
      const d = await api.sessions()
      sessions = d.sessions
      error = ''
    } catch (e) {
      error = String(e)
    }
  }

  onMount(() => {
    load()
    timer = setInterval(load, 5000) // 每 5 秒自动刷新,新攻击实时出现
    return () => clearInterval(timer)
  })

  const fmtTime = (ts) => new Date(ts * 1000).toLocaleString()
  const fmtDur = (s) =>
    s.end_ts ? `${Math.round(s.end_ts - s.start_ts)}s` : '进行中'
</script>

{#if error}<p class="err">API 错误:{error}</p>{/if}

<table>
  <thead>
    <tr>
      <th>ID</th><th>协议</th><th>来源 IP</th><th>端口</th>
      <th>开始时间</th><th>时长</th><th>事件</th><th>认证尝试</th>
    </tr>
  </thead>
  <tbody>
    {#each sessions as s (s.id)}
      <tr onclick={() => onSelect(s.id)}>
        <td>{s.id}</td>
        <td><span class="badge" class:ssh={s.protocol === 'ssh'}>{s.protocol.toUpperCase()}</span></td>
        <td class="mono">{s.src_ip}</td>
        <td class="mono">{s.src_port}</td>
        <td>{fmtTime(s.start_ts)}</td>
        <td>{fmtDur(s)}</td>
        <td>{s.event_count}</td>
        <td>{s.auth_count}</td>
      </tr>
    {:else}
      <tr><td colspan="8" class="empty">暂无会话 —— 等待扫描者上门…</td></tr>
    {/each}
  </tbody>
</table>

<style>
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #232b35; }
  th { color: #7d8a99; font-weight: 500; font-size: 12px; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #1a2230; }
  .mono { font-family: ui-monospace, Menlo, monospace; }
  .badge {
    background: #8a5a00; color: #ffd58a; font-size: 11px;
    padding: 2px 8px; border-radius: 4px;
  }
  .badge.ssh { background: #144a75; color: #7cc4ff; }
  .empty { text-align: center; color: #5c6a7a; padding: 40px 0; }
  .err { color: #ff7a7a; }
</style>
