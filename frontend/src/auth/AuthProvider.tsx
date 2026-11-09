import { KindeProvider, useKindeAuth } from '@kinde-oss/kinde-auth-react'
import type { ReactNode } from 'react'

import { setAccessTokenGetter } from '../api/client'

export function TokenBridge({ children }: { children: ReactNode }) {
  const { getAccessToken } = useKindeAuth()
  // Set during render so it is in place before any child query fires.
  setAccessTokenGetter(getAccessToken)
  return children
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <KindeProvider
      clientId={import.meta.env.VITE_KINDE_CLIENT_ID}
      domain={import.meta.env.VITE_KINDE_DOMAIN}
      audience={import.meta.env.VITE_KINDE_AUDIENCE}
      redirectUri={window.location.origin}
      logoutUri={window.location.origin}
      // On a kinde.com domain Kinde can't set its refresh cookie for us, so keep the refresh
      // token in localStorage (see README: a custom auth domain removes the need).
      useInsecureForRefreshToken={import.meta.env.VITE_KINDE_DOMAIN?.endsWith('.kinde.com')}
    >
      <TokenBridge>{children}</TokenBridge>
    </KindeProvider>
  )
}
