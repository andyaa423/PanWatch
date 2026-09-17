import { describe, expect, it } from 'vitest'
import { buildKlineSuggestion, volumeConfirmation } from './kline-scorer'

describe('volumeConfirmation', () => {
  it('uses AND to confirm and OR to weaken a bullish trend', () => {
    expect(volumeConfirmation(10, 60, 'bull')).toBe(1)
    expect(volumeConfirmation(-10, 60, 'bull')).toBe(-1)
    expect(volumeConfirmation(10, 40, 'bull')).toBe(-1)
  })

  it('checks confirmation before weakening for a contradictory boundary', () => {
    // OBV 走弱而 MFI >=55：确认不成立，随后由削弱 OR 命中。
    expect(volumeConfirmation(-1, 55, 'bull')).toBe(-1)
  })

  it('does not invent a signal when either factor is absent', () => {
    expect(volumeConfirmation(undefined, 60, 'bull')).toBe(0)
    expect(volumeConfirmation(10, undefined, 'bull')).toBe(0)
  })
})

describe('buildKlineSuggestion', () => {
  it('shows trend and volume confirmation as separate score components', () => {
    const result = buildKlineSuggestion({
      trend: '多头排列', macd_status: '金叉', macd_hist: 1,
      kdj_status: '金叉', obv_change: -1, mfi: 55,
    }, true)
    expect(result.trend_score).toBe(6)
    expect(result.volume_confirmation).toBe(-1)
    expect(result.score).toBe(result.trend_score + result.volume_confirmation + result.other_score)
    expect(result.evidence.some((item) => item.text.includes('量能削弱'))).toBe(true)
  })
})
