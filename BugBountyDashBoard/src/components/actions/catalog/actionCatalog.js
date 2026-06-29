import {
  Bug,
  Database,
  FileCode,
  Globe,
  Network,
  Search,
  Shield,
} from 'lucide-react'

const CAPABILITY_UI = {
  subfinder: {
    icon: Search,
    color: 'blue',
    description: 'Passive subdomain discovery',
  },
  httpx: {
    icon: Globe,
    color: 'green',
    description: 'Safe HTTP probing',
  },
  gau: {
    icon: Database,
    color: 'purple',
    description: 'Archived URL discovery',
  },
  katana: {
    icon: Network,
    color: 'red',
    description: 'Web crawling',
  },
  playwright: {
    icon: Globe,
    color: 'pink',
    description: 'Browser crawl with network capture',
  },
  linkfinder: {
    icon: FileCode,
    color: 'yellow',
    description: 'JavaScript endpoint extraction',
  },
  mantra: {
    icon: Shield,
    color: 'orange',
    description: 'JavaScript secret analysis',
  },
  ffuf: {
    icon: Bug,
    color: 'cyan',
    description: 'Light content discovery',
  },
  amass: {
    icon: Search,
    color: 'indigo',
    description: 'Infrastructure enumeration',
  },
  dnsx: {
    icon: Network,
    color: 'teal',
    description: 'DNS validation',
  },
  'dnsx-ptr': {
    icon: Network,
    color: 'teal',
    description: 'Reverse DNS lookup',
  },
  subjack: {
    icon: Shield,
    color: 'rose',
    description: 'Subdomain takeover check',
  },
  asnmap: {
    icon: Network,
    color: 'violet',
    description: 'ASN and CIDR discovery',
  },
  mapcidr: {
    icon: Database,
    color: 'slate',
    description: 'CIDR expansion',
  },
  naabu: {
    icon: Network,
    color: 'amber',
    description: 'Port discovery',
  },
}

const OPTION_UI = {
  active: { label: 'Active enumeration', type: 'checkbox' },
  count: { label: 'Count', type: 'number', min: 1 },
  depth: { label: 'Depth', type: 'number', min: 1, max: 10 },
  exclude_cdn: { label: 'Exclude CDN/WAF', type: 'checkbox' },
  headless: { label: 'Headless browser', type: 'checkbox' },
  host_count: { label: 'Host count', type: 'number', min: 1 },
  include_subs: { label: 'Include subdomains', type: 'checkbox' },
  js_crawl: { label: 'JavaScript crawl', type: 'checkbox' },
  mode: { label: 'Mode', type: 'text' },
  ports: { label: 'Ports', type: 'text', placeholder: '80,443,8080' },
  probe: { label: 'Probe discovered hosts', type: 'checkbox' },
  rate: { label: 'Rate', type: 'number', min: 1 },
  scan_mode: { label: 'Scan mode', type: 'text' },
  scan_type: { label: 'Scan type', type: 'text' },
  shuffle: { label: 'Shuffle IPs', type: 'checkbox' },
  skip_base: { label: 'Skip base IPs', type: 'checkbox' },
  skip_broadcast: { label: 'Skip broadcast IPs', type: 'checkbox' },
  timeout: { label: 'Timeout (seconds)', type: 'number', min: 1 },
  top_ports: { label: 'Top ports', type: 'text' },
}

const PROFILE_OPTION_DEFAULTS = {
  'amass/passive-enum': { active: false, timeout: 1800 },
  'amass/active-enum': { active: true, timeout: 1800 },
  'dnsx/dns-validate': { mode: 'basic', timeout: 600 },
  'dnsx-ptr/reverse-dns': { mode: 'ptr', timeout: 600 },
  'subfinder/passive-recon': { probe: true, timeout: 600 },
  'gau/archive-url-discovery': { include_subs: true, timeout: 600 },
}

const PROFILE_OPTION_FIELDS = {
  'dnsx/dns-validate': {
    mode: { type: 'select', options: ['basic', 'deep'] },
  },
  'dnsx-ptr/reverse-dns': {
    mode: { type: 'select', options: ['ptr'] },
  },
}

function titleize(value) {
  return String(value || '')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function numericDefault(spec) {
  if (spec.default !== undefined && spec.default !== null) return spec.default
  return ''
}

function fieldFromOptionSpec(name, spec = {}, overrides = {}) {
  const staticUi = OPTION_UI[name] || {}
  const enumValues = Array.isArray(spec.enum) ? spec.enum : []
  const type = enumValues.length
    ? 'select'
    : spec.type === 'boolean'
      ? 'checkbox'
      : spec.type === 'integer' || spec.type === 'number'
        ? 'number'
        : 'text'

  return {
    ...staticUi,
    name,
    label: staticUi.label || titleize(name),
    type,
    options: enumValues.length ? enumValues : staticUi.options,
    min: spec.minimum ?? staticUi.min,
    max: spec.maximum ?? staticUi.max,
    placeholder: staticUi.placeholder,
    required: Boolean(spec.required),
    defaultValue:
      spec.default !== undefined && spec.default !== null
        ? spec.default
        : staticUi.defaultValue,
    ...overrides,
  }
}

function fieldFromAllowedOption(name, detail) {
  const profileKey = `${detail.capability}/${detail.profile}`
  const overrides = PROFILE_OPTION_FIELDS[profileKey]?.[name] || {}
  const staticUi = OPTION_UI[name] || {}
  return {
    name,
    label: staticUi.label || titleize(name),
    type: staticUi.type || 'text',
    placeholder: staticUi.placeholder,
    min: staticUi.min,
    max: staticUi.max,
    options: staticUi.options,
    ...overrides,
  }
}

function defaultForField(field, detail) {
  const profileKey = `${detail.capability}/${detail.profile}`
  const profileDefaults = PROFILE_OPTION_DEFAULTS[profileKey] || {}
  if (field.name in profileDefaults) return profileDefaults[field.name]
  if (field.defaultValue !== undefined) return field.defaultValue
  if (field.type === 'checkbox') return false
  if (field.type === 'select') return field.options?.[0] ?? ''
  return ''
}

function optionFields(detail) {
  const schema = detail.option_schema || {}
  const schemaNames = Object.keys(schema)
  if (schemaNames.length > 0) {
    return schemaNames.map(name => fieldFromOptionSpec(name, schema[name]))
  }

  return (detail.allowed_options || []).map(name => fieldFromAllowedOption(name, detail))
}

function targetField(detail) {
  const frontend = detail.frontend || {}
  return {
    name: 'targets',
    label: frontend.target_label || 'Targets',
    type: 'textarea',
    placeholder: frontend.target_placeholder || 'one per line',
    required: true,
    asArray: true,
  }
}

export function buildActionFromCatalogDetail(detail) {
  const frontend = detail.frontend || {}
  const ui = CAPABILITY_UI[detail.capability] || {
    icon: Search,
    color: 'blue',
    description: detail.profile_label || detail.capability_label,
  }
  const fields = [targetField(detail), ...optionFields(detail)]
  const initialValues = fields.reduce((values, field) => {
    values[field.name] = field.name === 'targets' ? '' : defaultForField(field, detail)
    return values
  }, {})

  return {
    id: detail.id,
    catalogId: detail.id,
    capability: detail.capability,
    profile: detail.profile,
    name: frontend.name || detail.capability_label || titleize(detail.capability),
    description:
      frontend.description ||
      ui.description ||
      detail.profile_label ||
      titleize(detail.profile),
    badge: detail.profile_label || titleize(detail.profile),
    icon: ui.icon,
    color: frontend.color || ui.color,
    fields,
    initialValues,
    requiresApproval: detail.requires_approval,
    safetyLevel: detail.safety_level,
    scopePolicy: detail.scope_policy,
  }
}
