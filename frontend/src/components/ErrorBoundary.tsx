import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  failed: boolean
}

/** Shows a friendly message instead of a blank page if a screen throws while rendering. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Render error', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children
    return (
      <div role="alert" className="flex flex-col items-center gap-4 py-32 text-center">
        <p className="text-xl font-medium">Something went wrong on this page</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active"
        >
          Reload
        </button>
      </div>
    )
  }
}
