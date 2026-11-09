import { vi } from 'vitest'

// The API client captures fetch when it loads, so this is installed from the setup file
// before any test imports it.
export const fetchMock = vi.fn<typeof fetch>()

type Handler = (request: Request) => Response | Promise<Response>

/** Route fetches by "METHOD /path"; anything unrouted gets a 501. */
export function mockApi(routes: Record<string, Handler>) {
  fetchMock.mockImplementation(async (input, init) => {
    const request = input instanceof Request ? input : new Request(input, init)
    const key = `${request.method} ${new URL(request.url).pathname}`
    const handler = routes[key]
    return handler ? handler(request) : new Response(`Not mocked: ${key}`, { status: 501 })
  })
}

export const kindeAuth = {
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  getAccessToken: vi.fn(async () => 'test-token'),
}

export function signIn() {
  kindeAuth.isAuthenticated = true
}

export function resetMocks() {
  fetchMock.mockReset()
  kindeAuth.isAuthenticated = false
  kindeAuth.isLoading = false
  kindeAuth.login.mockReset()
  kindeAuth.register.mockReset()
  kindeAuth.logout.mockReset()
}
