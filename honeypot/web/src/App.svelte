<script>
  import SessionList from './lib/SessionList.svelte'
  import Replay from './lib/Replay.svelte'
  import Stats from './lib/Stats.svelte'

  let tab = $state('sessions')
  let selected = $state(null) // 选中的会话 id

  function openSession(id) {
    selected = id
    tab = 'replay'
  }
</script>

<div class="layout">
  <header>
    <h1>🍯 蜜罐控制台</h1>
    <nav>
      <button class:active={tab === 'sessions'} onclick={() => (tab = 'sessions')}>会话</button>
      <button class:active={tab === 'replay'} onclick={() => (tab = 'replay')} disabled={!selected}>回放</button>
      <button class:active={tab === 'stats'} onclick={() => (tab = 'stats')}>统计</button>
    </nav>
  </header>

  <main>
    {#if tab === 'sessions'}
      <SessionList onSelect={openSession} />
    {:else if tab === 'replay' && selected}
      <Replay sessionId={selected} />
    {:else if tab === 'stats'}
      <Stats />
    {/if}
  </main>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, 'PingFang SC', 'Helvetica Neue', sans-serif;
    background: #0f1419;
    color: #d7dde4;
  }
  .layout { max-width: 1100px; margin: 0 auto; padding: 16px 24px; }
  header { display: flex; align-items: center; gap: 24px; border-bottom: 1px solid #232b35; padding-bottom: 12px; }
  h1 { font-size: 20px; margin: 0; }
  nav { display: flex; gap: 8px; }
  nav button {
    background: none; border: 1px solid #2c3644; color: #9aa7b4;
    padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 14px;
  }
  nav button.active { background: #1d6ce0; border-color: #1d6ce0; color: #fff; }
  nav button:disabled { opacity: 0.35; cursor: default; }
  main { padding-top: 16px; }
</style>
