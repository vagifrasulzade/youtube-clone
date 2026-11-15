import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Testing Library only auto-cleans when test globals are enabled; do it explicitly so
// every test starts with an empty document.
afterEach(() => {
  cleanup()
})
