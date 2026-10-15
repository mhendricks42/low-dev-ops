import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('checking…')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then((body: { status: string }) => setStatus(body.status))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main>
      <h1>Hello, LowDevOps</h1>
      <p role="status">API: {status}</p>
    </main>
  )
}
