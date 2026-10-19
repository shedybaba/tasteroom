import { describe, expect, it } from 'vitest'
import { briefToMarkdown, fitSummary, initials, safeUrl, typeLabel } from '../lib/format'
import { applyDisplay, buildDisplayMap, shownName } from '../lib/display'
import { parsePasted } from '../lib/tastes'
import type { PlanResponse, Recommendation, ResolvedTaste } from '../types'

const rec = (why: { member: string; score: number }[], tags: string[] = []): Recommendation => ({
  entity: { id: 'X', name: 'X', type: 'urn:entity:artist' } as Recommendation['entity'],
  domain: 'music', explanation_method: 'qloo_explainability', shared_tags: tags,
  why: why.map((w) => ({ ...w, via: [] })),
})

describe('parsePasted', () => {
  it('parses "Name: a, b" lines and ignores blanks', () => {
    const m = parsePasted('Ada: Burna Boy, Nike\n\n  Tunde : Wizkid; Money Heist ')
    expect(m).toHaveLength(2)
    expect(m[0]).toEqual({ name: 'Ada', tastes: [{ text: 'Burna Boy', kind: 'any' }, { text: 'Nike', kind: 'any' }] })
    expect(m[1].name).toBe('Tunde')
    expect(m[1].tastes.map((t) => t.text)).toEqual(['Wizkid', 'Money Heist'])
  })
  it('names unnamed lines "Member N", caps tastes at 6 and members at 15', () => {
    const m = parsePasted('a, b, c, d, e, f, g, h')
    expect(m[0].name).toBe('Member 1')
    expect(m[0].tastes).toHaveLength(6)
    expect(parsePasted(Array.from({ length: 20 }, (_, i) => `M${i}: x`).join('\n'))).toHaveLength(15)
  })
  it('keeps colons inside taste text and drops members with no tastes', () => {
    expect(parsePasted('Jonas: Cyberpunk: Edgerunners')[0].tastes[0].text).toBe('Cyberpunk: Edgerunners')
    expect(parsePasted('Ada:\nTunde: Wizkid')).toHaveLength(1)
  })
})

describe('fitSummary', () => {
  it('says who a pick stands out for, else that it suits everyone', () => {
    expect(fitSummary(rec([{ member: 'Ada', score: 0.4 }, { member: 'Tunde', score: 0.3 }, { member: 'Seun', score: 0.3 }]))).toBe('Stands out for Ada')
    expect(fitSummary(rec([{ member: 'A', score: 0.34 }, { member: 'B', score: 0.33 }, { member: 'C', score: 0.33 }]))).toBe('A crowd-pleaser: fits all 3 members')
    expect(fitSummary(rec([], ['Afrobeats']))).toBe('Shares Afrobeats')
  })
})

describe('safeUrl', () => {
  it('allows http(s) and rejects script/data/garbage', () => {
    expect(safeUrl('https://lekkileisure.com/')).toBe('https://lekkileisure.com/')
    expect(safeUrl('http://example.com')).toBe('http://example.com/')
    expect(safeUrl('javascript:alert(1)')).toBeNull()
    expect(safeUrl('data:text/html,<script>1</script>')).toBeNull()
    expect(safeUrl('not a url')).toBeNull()
    expect(safeUrl(null)).toBeNull()
  })
})

describe('helpers', () => {
  it('labels types and initials', () => {
    expect(typeLabel('urn:entity:tv_show')).toBe('TV show')
    expect(typeLabel('urn:entity:videogame')).toBe('Game')
    expect(initials('Burna Boy')).toBe('BB')
  })
  it('exports the brief as Markdown without empty sections', () => {
    const plan = {
      request: { community_name: 'Pixel Pact', city: 'Austin' },
      brief: { title: 'T', concept: 'C', vibe_words: ['a', 'b'], run_of_show: ['one', 'two'], promo_line: 'Join!',
        music: [{ entity_id: '1', name: 'Mr Eazi', reason: 'fits' }], venue: [], sponsors: [], content: [] },
    } as unknown as PlanResponse
    const md = briefToMarkdown(plan)
    expect(md).toContain('# T')
    expect(md).toContain('1. one\n2. two')
    expect(md).toContain('- **Mr Eazi**: fits')
    expect(md).not.toContain('## Venue')
  })
})


describe('display names (the member\'s own spelling)', () => {
  const rt = (input: string, name: string): ResolvedTaste =>
    ({ member: 'Ada', input, entity: { id: name, name } as ResolvedTaste['entity'] })

  it('maps Qloo casing back to what the member typed, only for case-only differences', () => {
    const map = buildDisplayMap([rt('Tems', 'TEms'), rt('Apple', 'Apple Inc'), rt('Burna Boy', 'Burna Boy'), rt('  wizkid ', 'Wizkid')])
    expect([...map.entries()]).toEqual([['TEms', 'Tems'], ['Wizkid', 'wizkid']])  // a real rename (Apple Inc) is left alone
  })
  it('replaces whole words in text only', () => {
    const map = buildDisplayMap([rt('Tems', 'TEms')])
    expect(applyDisplay('Stands out for Ada (via TEms, Burna Boy)', map)).toBe('Stands out for Ada (via Tems, Burna Boy)')
    expect(applyDisplay('NOTEMSHERE and TEmsley', map)).toBe('NOTEMSHERE and TEmsley')
  })
  it('shownName keeps the member text for case-only matches and Qloo\'s name otherwise', () => {
    expect(shownName('Tems', 'TEms')).toBe('Tems')
    expect(shownName('Apple', 'Apple Inc')).toBe('Apple Inc')
  })
})
