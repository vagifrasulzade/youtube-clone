import { describe, expect, it } from 'vitest'

import { durationLabel } from './duration'

describe('durationLabel', () => {
  it.each([
    [0, '0:00'],
    [8, '0:08'],
    [65, '1:05'],
    [599, '9:59'],
    [3600, '1:00:00'],
    [3725, '1:02:05'],
  ])('%i seconds -> %s', (seconds, label) => {
    expect(durationLabel(seconds)).toBe(label)
  })

  it('is empty when the duration is unknown', () => {
    expect(durationLabel(null)).toBe('')
    expect(durationLabel(undefined)).toBe('')
  })
})
