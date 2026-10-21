import { describe, expect, it } from 'vitest'
import { isWebhookUrl, pollText, pollVenues, sharePath } from '../lib/share'
import { coverageCell } from '../lib/coverage'
import { inLineup, personalCardSummary, personalDetail, personalFit, personalForDomain, personalLabel, personalLine, personalMembers, personalRow } from '../lib/personal'
import { briefToMarkdown, fitSummary, initials, safeUrl, typeLabel } from '../lib/format'
import { applyDisplay, buildDisplayMap, capName, shownName } from '../lib/display'
import { capNote, clearJoined, DEMO_ROOM, inviteMessage, joinedAs, joinPath, loadRooms, markJoined, organizerPath, responseCountText, saveRoom } from '../lib/rooms'
import { changeLine, changeText, QUICK_REFINEMENTS, versionLabel } from '../lib/refine'
import { assignSlots, ideasFor, kindFromType, parsePasted, slotForKind, tasteHint, toRequestMember } from '../lib/tastes'
import type { PersonalPick, PersonalSkip, PlanResponse, Recommendation, ResolvedTaste, Taste } from '../types'

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
  it('capitalises member names for display without touching the stored text', () => {
    expect(capName('kelechi')).toBe('Kelechi')
    expect(capName('ada obi')).toBe('Ada Obi')
    expect(capName("o'brien")).toBe("O'Brien")
    expect(capName('Ada')).toBe('Ada')
    expect(capName('éloïse')).toBe('Éloïse')
    const map = buildDisplayMap([], ['kelechi', 'Ada', 'will'])
    expect(applyDisplay('Stands out for kelechi & Ada. It will fit; will is a name.', map)).toBe('Stands out for Kelechi & Ada. It will fit; will is a name.')
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

describe('invite rooms helpers', () => {
  const fakeStorage = (initial: Record<string, string> = {}) => {
    const data = { ...initial }
    return { data, getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, removeItem: (k: string) => { delete data[k] } }
  }

  it('builds links; the organizer token is URL-encoded', () => {
    expect(joinPath('abc23xyz')).toBe('/join/abc23xyz')
    expect(organizerPath('abc23xyz', 'a b/c+d')).toBe('/room/abc23xyz?t=a%20b%2Fc%2Bd')
    expect(organizerPath(DEMO_ROOM.slug, DEMO_ROOM.token)).toBe('/room/demo?t=demo-room')
  })

  it('writes a copy-ready invite message that ends with the link', () => {
    const m = inviteMessage({ community: 'Pixel Pact', goal: 'an anime watch party', city: 'Austin', url: 'https://x.test/join/abc' })
    expect(m).toContain('an anime watch party for Pixel Pact in Austin')
    expect(m.split('\n').pop()).toBe('https://x.test/join/abc')
    expect(m).toMatch(/30 seconds, no sign-up/)
  })

  it('remembers up to 5 rooms, newest first, one per slug', () => {
    const s = fakeStorage()
    for (let i = 0; i < 7; i++) saveRoom({ slug: `r${i}`, token: `t${i}`, name: `Room ${i}`, city: 'Lagos' }, s, 1000 + i)
    expect(loadRooms(s).map((r) => r.slug)).toEqual(['r6', 'r5', 'r4', 'r3', 'r2'])
    saveRoom({ slug: 'r3', token: 'new', name: 'Renamed', city: 'Lagos' }, s, 5000)
    const after = loadRooms(s)
    expect(after[0]).toMatchObject({ slug: 'r3', token: 'new', name: 'Renamed' })
    expect(after.filter((r) => r.slug === 'r3')).toHaveLength(1)
  })

  it('survives corrupt, wrong-shaped or blocked storage', () => {
    expect(loadRooms(fakeStorage({ 'tasteroom.rooms': '{not json' }))).toEqual([])
    expect(loadRooms(fakeStorage({ 'tasteroom.rooms': '{"a":1}' }))).toEqual([])
    expect(loadRooms(fakeStorage({ 'tasteroom.rooms': JSON.stringify([{ slug: 'ok', token: 't' }, { slug: 5 }, null]) })).map((r) => r.slug)).toEqual(['ok'])
    const blocked = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') }, removeItem: () => { throw new Error('denied') } }
    expect(loadRooms(blocked)).toEqual([])
    expect(() => saveRoom({ slug: 'x', token: 'y', name: 'z', city: 'c' }, blocked)).not.toThrow()
    expect(joinedAs('x', blocked)).toBeNull()
    expect(() => markJoined('x', 'Ada', blocked)).not.toThrow()
    expect(() => clearJoined('x', blocked)).not.toThrow()
  })

  it('tracks "already joined on this phone" per room', () => {
    const s = fakeStorage()
    expect(joinedAs('r1', s)).toBeNull()
    markJoined('r1', 'Ada', s)
    expect(joinedAs('r1', s)).toBe('Ada')
    expect(joinedAs('r2', s)).toBeNull()
    clearJoined('r1', s)
    expect(joinedAs('r1', s)).toBeNull()
  })

  it('phrases the response count and the 15-member cap note', () => {
    expect([0, 1, 9].map(responseCountText)).toEqual(['No responses yet', '1 member responded', '9 members responded'])
    expect(capNote(12, 12, [])).toBeNull()
    expect(capNote(18, 15, ['Zed', 'Yu', 'Al'])).toBe('18 responded. TasteRoom uses the 15 whose tastes Qloo matched best (left out: Zed, Yu, Al).')
  })
})

describe('refinement copy helpers', () => {
  const change = (domain: 'music' | 'venues' | 'brands' | 'content', swapped: number, note: string | null = null) => ({ domain, swapped, of: 3, note })

  it('quick refinements are the five from the spec, each long enough for the API (3+ characters)', () => {
    expect(QUICK_REFINEMENTS).toEqual(['Cheaper venue', 'More hidden gems', 'Swap the music vibe: more chill',
      'Add a watch-party content theme', 'Different neighbourhood'])
    expect(QUICK_REFINEMENTS.every((q) => q.length >= 3 && q.length <= 200)).toBe(true)
  })

  it('says how many picks were swapped, and plainly when none were', () => {
    expect(changeText(change('venues', 3))).toBe('Venues: 3 swapped')
    expect(changeText(change('brands', 0))).toBe('Sponsors: re-checked, same picks')
  })

  it('builds the one-line summary with what was applied', () => {
    const r = { instruction: 'More hidden gems', trace_start: 4, changes: [change('music', 3, 'hidden gems on'), change('brands', 2, 'hidden gems on')] }
    expect(changeLine(r)).toBe('Music: 3 swapped (hidden gems on) · Sponsors: 2 swapped (hidden gems on)')
    expect(changeLine({ ...r, changes: [change('venues', 1)] })).toBe('Venues: 1 swapped')
  })

  it('labels versions; the first plan of an example says so', () => {
    expect(versionLabel({ version: 1, example: true })).toBe('v1 (example)')
    expect(versionLabel({ version: 2, example: false })).toBe('v2')
  })
})

describe('coverage text', () => {
  const cov = (covered: number, total: number, unmeasurable = 0, standout = 0, personal = 0, inLineup = 0) =>
    ({ members: [], covered, standout, personal, in_lineup: inLineup, total, unmeasurable, balance: [] })

  it('has no Compare cell when coverage is missing or there is nobody to compare', () => {
    expect(coverageCell(undefined)).toBeNull()
    expect(coverageCell(cov(1, 1))).toBeNull()
    expect(coverageCell(cov(8, 8, 0, 1, 8))).toEqual({ covered: 8, total: 8, standout: 1, personal: 8 })
  })
})

describe('personal picks', () => {
  const ent = (id: string, name: string) => ({ id, name, type: 'urn:entity:artist' }) as unknown as PersonalPick['entity']
  const pp = (member: string, domain: 'music' | 'content', id: string, name: string): PersonalPick =>
    ({ member, domain, entity: ent(id, name), via: ['X'], member_rank: 1, fit: 'in_group_results', group_rank: 2, group_ratio: 1, explanation: `why ${name}` })
  const plan = (personal: PersonalPick[], skipped: PersonalSkip[] = [], briefIds: string[] = []) => ({
    request: { members: [{ name: 'Ada' }, { name: 'Bo' }, { name: 'Cy' }] },
    personal, personal_skipped: skipped,
    brief: { music: briefIds.map((entity_id) => ({ entity_id, name: entity_id, reason: '' })), venue: [], sponsors: [], content: [], title: 'T', concept: 'C', vibe_words: [], run_of_show: [], promo_line: 'P' },
  }) as unknown as PlanResponse
  const skip = (member: string, domain: 'music' | 'content', note: string): PersonalSkip => ({ member, domain, reason: 'none_fit_group', note })

  it('shows each member\u2019s music pick, else their content pick, else why they have none', () => {
    const rows = personalRow(plan([pp('Ada', 'content', 'c1', 'Show'), pp('Ada', 'music', 'm1', 'Song'), pp('Bo', 'content', 'c2', 'Podcast')], [skip('Cy', 'music', 'too far')]))
    expect(rows.map((r) => [r.member, r.pick?.entity.name ?? null, r.missing])).toEqual([['Ada', 'Song', null], ['Bo', 'Podcast', null], ['Cy', null, 'too far']])
  })

  it('never drops a member from the row: an unexplained gap still gets a message', () => {
    expect(personalRow(plan([])).map((r) => r.missing)).toEqual(Array(3).fill('No personal pick could be made for them.'))
  })

  it('a domain tab lists that domain\u2019s picks in the organizer\u2019s member order, plus who has none there', () => {
    const r = personalForDomain(plan([pp('Cy', 'music', 'm3', 'C'), pp('Ada', 'music', 'm1', 'A'), pp('Bo', 'content', 'c2', 'P')], [skip('Bo', 'music', 'none')]), 'music')
    expect(r.picks.map((p) => p.member)).toEqual(['Ada', 'Cy'])
    expect(r.missing.map((s) => s.member)).toEqual(['Bo'])
  })

  it('knows whether a personal pick is already in the brief\u2019s main lineup', () => {
    const p = plan([pp('Ada', 'music', 'm1', 'A')], [], ['m1'])
    expect(inLineup(p, p.personal![0])).toBe(true)
    expect(inLineup(plan([pp('Ada', 'music', 'm1', 'A')], [], ['other']), pp('Ada', 'music', 'm1', 'A'))).toBe(false)
  })

  it('labels the card for the member', () => {
    expect(personalLabel('Ada')).toBe('Personal pick for Ada')
  })

  it('writes the card as one line naming up to three of their tastes, then "Fits the group too."', () => {
    const p = { ...pp('Ada', 'music', 'm1', 'Song'), via: ['A', 'B', 'C', 'D'] }
    expect(personalLine(p)).toBe("Picked from Ada's tastes: A, B, C. Fits the group too.")
    expect(personalLine({ ...p, via: ['Demon Slayer: Kimetsu no Yaiba', 'Hikaru Utada', 'Skrillex'] })).toBe("Picked from Ada's tastes: Demon Slayer: Kimetsu no Yaiba, Hikaru Utada. Fits the group too.")
    expect(personalLine({ ...p, via: [] })).toBe("Picked from Ada's tastes. Fits the group too.")
    expect(personalLine({ ...p, member: 'ada' }, capName)).toBe("Picked from Ada's tastes: A, B, C. Fits the group too.")
  })

  it('keeps the numbers (rank, fit) for the "Why?" panel', () => {
    const base = { ...pp('Ada', 'music', 'm1', 'Song'), member_rank: 3 }
    expect(personalDetail({ ...base, group_rank: 2 })).toEqual(["Qloo's #3 result for Ada's tastes on their own.", "It is #2 in the group's music results."])
    expect(personalDetail({ ...base, domain: 'content', fit: 'group_affinity', group_rank: null, group_ratio: 0.972 })[1]).toBe("Qloo ties it to the group at 97% of the group's average pull.")
    expect(personalDetail({ ...base, fit: 'group_affinity', group_rank: null, group_ratio: 1.01 })[1]).toBe("Qloo ties it to the group as strongly as the group's average pick.")
  })

  const rec = (scores: Record<string, number>) => ({ entity: ent('m1', 'Song'), domain: 'music', explanation_method: 'qloo_explainability', shared_tags: [],
    why: Object.entries(scores).map(([member, score]) => ({ member, score, via: [] })) }) as unknown as Recommendation

  it('finds whose personal pick an entity is, per domain', () => {
    const p = plan([pp('Ada', 'music', 'm1', 'Song'), pp('Bo', 'content', 'm1', 'Song')])
    expect(personalMembers(p, 'music', 'm1')).toEqual(['Ada'])
    expect(personalMembers(p, 'content', 'm1')).toEqual(['Bo'])
    expect(personalMembers(p, 'music', 'zzz')).toEqual([])
  })

  it('tab-card wording mirrors the brief row: member first, then only what the group data supports', () => {
    expect(personalFit(rec({ Ada: 0.2, Tessa: 0.5, Omar: 0.3 }), ['Ada'])).toBe('Also stands out for Tessa')
    expect(personalFit(rec({ Ada: 0.6, Tessa: 0.2, Omar: 0.2 }), ['Ada'])).toBeNull()
    expect(personalFit(rec({ Ada: 0.34, Tessa: 0.33, Omar: 0.33 }), ['Ada'])).toBe('A crowd-pleaser: fits all 3 members')
    expect(personalFit(rec({ Ada: 1 }), ['Ada'])).toBeNull()
    expect(personalFit(undefined, ['Ada'])).toBeNull()
    expect(personalCardSummary(rec({ Ada: 0.2, Tessa: 0.5, Omar: 0.3 }), ['ada'], capName)).toBe('Personal pick for Ada. Also stands out for Tessa')
    expect(personalCardSummary(rec({ Ada: 0.6, Tessa: 0.2, Omar: 0.2 }), ['Ada'])).toBe('Personal pick for Ada')
  })

  it('adds a "Something for everyone" section to the Markdown export, one line per member that has a pick', () => {
    const md = briefToMarkdown(plan([pp('Ada', 'music', 'm1', 'Song'), pp('Cy', 'content', 'c3', 'Show')]))
    expect(md).toContain('## Something for everyone')
    expect(md).toContain('- **Song** (personal pick for Ada): why Song')
    expect(md).toContain('- **Show** (personal pick for Cy): why Show')
    expect(md).not.toContain('personal pick for Bo')
    expect(briefToMarkdown(plan([]))).not.toContain('Something for everyone')
  })
})

describe('sharing', () => {
  const venue = (id: string, name: string, neighborhood: string | null, address: string | null = null) =>
    ({ entity: { id, name, neighborhood, address } as Recommendation['entity'], domain: 'venues', why: [], shared_tags: [], explanation_method: 'qloo_explainability' }) as Recommendation
  const plan = (briefIds: string[], ranked: Recommendation[]) => ({
    request: { community_name: 'Lagos Creators' }, recommendations: { venues: ranked },
    brief: { title: 'Launch Night', venue: briefIds.map((id) => ({ entity_id: id, name: `brief ${id}`, reason: '' })) },
  }) as unknown as PlanResponse

  it('links examples to their own page and every other plan to the read-only view', () => {
    expect(sharePath('lagos-creators', true)).toBe('/example/lagos-creators')
    expect(sharePath('abc123', false)).toBe('/plan/abc123?shared=1')
  })

  it('accepts only real Discord webhook URLs (same rule as the server)', () => {
    const tok = 'T0kenAbCdEfGhIjKlMnOpQrStUvWxYz-_0123456789'
    expect(isWebhookUrl(`https://discord.com/api/webhooks/1234567890123456789/${tok}`)).toBe(true)
    expect(isWebhookUrl(`  https://canary.discordapp.com/api/v10/webhooks/1234567890123456789/${tok}/ `)).toBe(true)
    for (const bad of ['', 'hello', `http://discord.com/api/webhooks/1234567890123456789/${tok}`, `https://evil.example/api/webhooks/1234567890123456789/${tok}`,
      `https://discord.com.evil.example/api/webhooks/1234567890123456789/${tok}`, `https://discord.com@evil.example/api/webhooks/1234567890123456789/${tok}`,
      `https://discord.com/api/webhooks/1234567890123456789/${tok}?thread_id=1`, 'https://discord.com/api/webhooks/12/short']) expect(isWebhookUrl(bad)).toBe(false)
  })

  it('polls the brief\u2019s venues first, then the next-ranked ones, never more than 3 and never twice', () => {
    const ranked = [venue('a', 'Alpha', 'Ikoyi'), venue('b', 'Bravo', null, '5 Bar Rd, Lagos'), venue('c', 'Charlie', 'Maroko'), venue('d', 'Delta', null)]
    expect(pollVenues(plan(['c'], ranked)).map((v) => v.name)).toEqual(['Charlie', 'Alpha', 'Bravo'])
    expect(pollVenues(plan(['a', 'b', 'c'], ranked)).map((v) => v.name)).toEqual(['Alpha', 'Bravo', 'Charlie'])
    expect(pollVenues(plan([], ranked))[1]).toEqual({ name: 'Bravo', where: '5 Bar Rd' })
    const long = [venue('x', 'Xray', null, `${'Very Long Street Name '.repeat(5)}, Lagos`), venue('y', 'Yankee', 'Ikoyi')]
    expect(pollVenues(plan([], long))[0].where!.length).toBeLessThanOrEqual(40)
    expect(pollVenues(plan([], long))[0].where).toMatch(/…$/)
  })

  it('writes ready-to-paste poll text with numbered options', () => {
    const text = pollText(plan(['a', 'b', 'c'], [venue('a', 'Alpha', 'Ikoyi'), venue('b', 'Bravo', null), venue('c', 'Charlie', 'Maroko')]))!
    expect(text.split('\n')).toEqual([
      '\u{1F4CD} Where should we hold Launch Night? Vote with a reaction:', '',
      '1\uFE0F\u20E3 Alpha (Ikoyi)', '2\uFE0F\u20E3 Bravo', '3\uFE0F\u20E3 Charlie (Maroko)', '', 'Picked from Qloo taste data for Lagos Creators.'])
  })

  it('offers no poll when there is nothing to choose between', () => {
    expect(pollText(plan(['a'], [venue('a', 'Alpha', 'Ikoyi')]))).toBeNull()
    expect(pollText(plan([], []))).toBeNull()
  })
})
