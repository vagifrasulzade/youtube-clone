import { useEffect } from 'react'

const APP = 'TubeClone'

/** Browser tab title like YouTube's ("<page> - TubeClone"); plain app name when empty. */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    document.title = title ? `${title} - ${APP}` : APP
  }, [title])
}
