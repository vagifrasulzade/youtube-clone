import { useEffect } from 'react'

import { APP_NAME } from '../brand'

/** Browser tab title like YouTube's ("<page> - YouTube Clone"); plain app name when empty. */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    document.title = title ? `${title} - ${APP_NAME}` : APP_NAME
  }, [title])
}
