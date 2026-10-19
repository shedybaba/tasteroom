import { describe, expect, it } from 'vitest'
import { briefToMarkdown, fitSummary, initials, safeUrl, typeLabel } from '../lib/format'
import { applyDisplay, buildDisplayMap, shownName } from '../lib/display'
import { assignSlots, ideasFor, kindFromType, parsePasted, slotForKind, tasteHint, toRequestMember } from '../lib/tastes'
import type { PlanResponse, Recommendation, ResolvedTaste, Taste } from '../types'

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

describe('guided slots', () => {
  const t = (text: string, kind: Taste['kind']): Taste => ({ text, kind })

  it('maps kinds to slots', () => {
    expect([slotForKind('artist'), slotForKind('tv_show'), slotForKind('movie'), slotForKind('brand'), slotForKind('podcast'), slotForKind('place')])
      .toEqual(['artist', 'show', 'show', 'brand', 'podcast', 'place'])
    expect([slotForKind('any'), slotForKind('video_game'), slotForKind('book')]).toEqual([null, null, null])
    expect(kindFromType('urn:entity:videogame')).toBe('video_game')
    expect(kindFromType('urn:entity:tv_show')).toBe('tv_show')
    expect(kindFromType('urn:entity:locality')).toBe('any')
  })

  it('assigns existing tastes to slots; repeats and unslotted kinds go to the free area', () => {
    const out = assignSlots([t('Burna Boy', 'artist'), t('Tems', 'artist'), t('Black Mirror', 'tv_show'), t('Inception', 'movie'),
      t('Nike', 'brand'), t('Elden Ring', 'video_game'), t('Pasted thing', 'any')])
    expect(out.map((x) => [x.text, x.slot])).toEqual([
      ['Burna Boy', 'artist'], ['Tems', 'extra'], ['Black Mirror', 'show'], ['Inception', 'extra'],
      ['Nike', 'brand'], ['Elden Ring', 'extra'], ['Pasted thing', 'extra']])
  })

  it('sends picked suggestions with their Qloo id and drops UI-only fields and empty text', () => {
    const pick = { id: 'ABC-123', name: 'TEms', type: 'urn:entity:artist', image: null, description: null, subtitle: null }
    const m = toRequestMember({ name: 'x', tastes: [
      { text: 'Tems', kind: 'artist', slot: 'artist', pick, entity_id: 'ABC-123' },
      { text: '  Nike ', kind: 'brand', slot: 'brand' }, { text: '   ', kind: 'any', slot: 'extra' },
      { text: 'Static idea', kind: 'podcast', slot: 'podcast', pick: { ...pick, id: null } }] }, 'Ada')
    expect(m).toEqual({ name: 'Ada', tastes: [
      { text: 'Tems', kind: 'artist', entity_id: 'ABC-123' }, { text: 'Nike', kind: 'brand' }, { text: 'Static idea', kind: 'podcast' }] })
    expect(JSON.stringify(m)).not.toMatch(/slot|pick/)
  })

  it('count hint: "N of 5 added", a soft warning under 2, never an empty string', () => {
    expect(tasteHint(3)).toEqual({ text: '3 of 5 added: more variety = better picks', warn: null })
    expect(tasteHint(1).warn).toMatch(/at least 2/)
    expect(tasteHint(0).warn).not.toBeNull()
    expect(tasteHint(6).text).toBe('6 added: more variety = better picks')
  })

  it('idea windows rotate per member so neighbours see different chips', () => {
    const list = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    expect(ideasFor(list, 0)).toEqual(['a', 'b', 'c', 'd'])
    expect(ideasFor(list, 1)).toEqual(['e', 'f', 'g', 'h'])
    expect(ideasFor(list, 2)).toEqual(['a', 'b', 'c', 'd'])
    expect(ideasFor(['x', 'y'], 5)).toEqual(['x', 'y'])
    expect(ideasFor(['a', 'b', 'c', 'd', 'e', 'f'], 1)).toEqual(['e', 'f', 'a', 'b'])  // wraps
  })
})
