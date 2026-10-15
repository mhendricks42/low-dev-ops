import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

test('shows the API status from /api/health', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'ok' })))
  render(<App />)
  expect(screen.getByRole('heading', { name: 'Hello, LowDevOps' })).toBeInTheDocument()
  expect(await screen.findByText('API: ok')).toBeInTheDocument()
})

test('reports an unreachable API', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')))
  render(<App />)
  expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
})
