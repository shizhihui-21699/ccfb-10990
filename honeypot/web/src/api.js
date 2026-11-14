const BASE = ''

async function get(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

export const api = {
  sessions: () => get('/api/sessions'),
  session: (id) => get(`/api/sessions/${id}`),
  stats: () => get('/api/stats'),
}
