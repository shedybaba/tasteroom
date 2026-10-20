import type { Brief, Domain, PlanResponse, Recommendation } from '../types'

export const DOMAIN_META: Record<Domain, { label: string; tab: string; blurb: string }> = {
  music: { label: 'Music', tab: 'Music', blurb: 'Artists your community will actually want on the bill.' },
  venues: { label: 'Venues', tab: 'Venues', blurb: 'Places in your city that match the group’s taste.' },
  brands: { label: 'Sponsors', tab: 'Sponsors', blurb: 'Brands your members already gravitate towards.' },
  content: { label: 'Content', tab: 'Content', blurb: 'Podcasts and shows for watch-party and talk-segment ideas.' },
}
export const DOMAIN_ORDER: Domain[] = ['music', 'venues', 'brands', 'content']

const TYPE_LABELS: Record<string, string> = {
  artist: 'Artist', place: 'Venue', brand: 'Brand', podcast: 'Podcast', tv_show: 'TV show',
  movie: 'Movie', book: 'Book', video_game: 'Game', videogame: 'Game',
}
export function typeLabel(urn: string): string {
  const key = urn.split(':').pop() ?? urn
  return TYPE_LABELS[key] ?? key
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')
}

export const pct = (n: number) => `${Math.round(n * 100)}%`

/** One honest line about who a pick suits, from the explanation data. Mirrors backend brief.py. */
export function fitSummary(rec: Recommendation): string {
  const n = rec.why.length
  const standout = rec.why.filter((c) => n > 1 && c.score >= 1.15 / n)
  if (standout.length) return `Stands out for ${standout.slice(0, 2).map((c) => c.member).join(' & ')}`
  if (n > 1) return `A crowd-pleaser: fits all ${n} members`
  if (n === 1) return `Suits ${rec.why[0].member}`
  return rec.shared_tags.length ? `Shares ${rec.shared_tags[0]}` : 'Recommended by Qloo'
}

export const METHOD_LABEL: Record<Recommendation['explanation_method'], string> = {
  qloo_explainability: 'Qloo explainability',
  per_member_affinity: 'Per-member affinity',
  tag_overlap: 'Shared tags',
}

/** "Something for everyone": one personal pick per member (music first), each with its data-built explanation. */
function everyone(plan: PlanResponse, fix: (s: string) => string): string {
  const picks = plan.personal ?? []
  if (!picks.length) return ''   // mock data, or a plan saved before personal picks existed
  const rows = plan.request.members.flatMap(({ name }) => {
    const p = picks.find((x) => x.member === name && x.domain === 'music') ?? picks.find((x) => x.member === name)
    return p ? [`- **${p.entity.name}** (personal pick for ${name}): ${fix(p.explanation)}`] : []
  })
  return rows.length ? `\n## Something for everyone\n${rows.join('\n')}\n` : ''
}

export function briefToMarkdown(plan: PlanResponse, fix: (s: string) => string = (s) => s): string {
  const b: Brief = plan.brief
  const picks = (title: string, items: Brief['music']) =>
    items.length ? `\n## ${title}\n${items.map((p) => `- **${p.name}**: ${fix(p.reason)}`).join('\n')}\n` : ''
  return [
    `# ${b.title}`,
    `*${plan.request.community_name} · ${plan.request.city}*`,
    `\n${b.concept}`,
    `\n**Vibe:** ${b.vibe_words.join(', ')}`,
    `\n## Run of show\n${b.run_of_show.map((l, i) => `${i + 1}. ${l}`).join('\n')}`,
    picks('Music', b.music), picks('Venue', b.venue), picks('Sponsors', b.sponsors), picks('Content', b.content),
    everyone(plan, fix),
    `\n## Announcement\n${b.promo_line}`,
    `\n_Picks sourced from Qloo taste data via TasteRoom._`,
  ].join('\n')
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** Only http(s) links are rendered as anchors: the value comes from third-party data. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const u = new URL(url)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null
  } catch {
    return null
  }
}
