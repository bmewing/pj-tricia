/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_KINDE_CLIENT_ID: string
  readonly VITE_KINDE_DOMAIN: string
  readonly VITE_KINDE_AUDIENCE: string
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
