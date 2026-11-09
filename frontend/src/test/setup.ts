import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { fetchMock, kindeAuth, resetMocks } from './mocks'

globalThis.fetch = fetchMock

vi.mock('@kinde-oss/kinde-auth-react', () => ({ useKindeAuth: () => kindeAuth }))

afterEach(() => {
  cleanup()
  resetMocks()
})

// jsdom gaps that Mantine relies on.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
})
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Element.prototype.scrollIntoView = () => {}
// An autosizing Textarea listens for web fonts loading.
Object.defineProperty(document, 'fonts', {
  value: { addEventListener: () => {}, removeEventListener: () => {} },
})
